use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use serde::Deserialize;

const PENDING_DATABASE: &str = "restore.pending.db";
const PENDING_MANIFEST: &str = "restore.pending.json";
const DESKTOP_SCHEMA_VERSION: i64 = 1;
const SQLITE_HEADER: &[u8; 16] = b"SQLite format 3\0";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PendingRestore {
    schema_version: i64,
}

fn timestamp() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

fn cleanup_pending(app_data: &Path) {
    let _ = fs::remove_file(app_data.join(PENDING_DATABASE));
    let _ = fs::remove_file(app_data.join(PENDING_MANIFEST));
    let _ = fs::remove_file(app_data.join("genesis.restore.tmp"));
}

fn sqlite_header_valid(path: &Path) -> Result<bool, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut header = [0_u8; 16];
    if file.read_exact(&mut header).is_err() {
        return Ok(false);
    }
    Ok(&header == SQLITE_HEADER)
}

fn remove_journals(database: &Path) {
    let database_text = database.to_string_lossy();
    let _ = fs::remove_file(PathBuf::from(format!("{database_text}-wal")));
    let _ = fs::remove_file(PathBuf::from(format!("{database_text}-shm")));
    let _ = fs::remove_file(PathBuf::from(format!("{database_text}-journal")));
}

pub fn apply_pending_restore(app_data: &Path) -> Result<Option<PathBuf>, String> {
    let pending = app_data.join(PENDING_DATABASE);
    let manifest_path = app_data.join(PENDING_MANIFEST);
    if !pending.exists() && !manifest_path.exists() {
        return Ok(None);
    }
    if !pending.is_file() || !manifest_path.is_file() {
        cleanup_pending(app_data);
        return Err("Incomplete Genesis restore staging data was discarded".into());
    }

    let manifest: PendingRestore = fs::read_to_string(&manifest_path)
        .map_err(|error| error.to_string())
        .and_then(|text| serde_json::from_str(&text).map_err(|error| error.to_string()))
        .map_err(|error| {
            cleanup_pending(app_data);
            format!("Invalid Genesis restore manifest was discarded: {error}")
        })?;

    if manifest.schema_version < 1 || manifest.schema_version > DESKTOP_SCHEMA_VERSION {
        cleanup_pending(app_data);
        return Err(format!(
            "Staged restore schema {} is incompatible with desktop schema {}; restore was not applied",
            manifest.schema_version, DESKTOP_SCHEMA_VERSION
        ));
    }
    if !sqlite_header_valid(&pending)? {
        cleanup_pending(app_data);
        return Err("Staged restore is not a SQLite database; restore was not applied".into());
    }

    fs::create_dir_all(app_data).map_err(|error| error.to_string())?;
    let database = app_data.join("genesis.db");
    let backups = app_data.join("backups");
    fs::create_dir_all(&backups).map_err(|error| error.to_string())?;

    let safety = if database.is_file() {
        let path = backups.join(format!("genesis-pre-restore-{}.db", timestamp()));
        fs::copy(&database, &path)
            .map_err(|error| format!("Could not create pre-restore safety backup: {error}"))?;
        Some(path)
    } else {
        None
    };

    let temporary = app_data.join("genesis.restore.tmp");
    if let Err(error) = fs::copy(&pending, &temporary) {
        cleanup_pending(app_data);
        return Err(format!("Could not stage the validated restore for replacement: {error}"));
    }

    remove_journals(&database);
    if database.exists() {
        if let Err(error) = fs::remove_file(&database) {
            let _ = fs::remove_file(&temporary);
            cleanup_pending(app_data);
            return Err(format!("Could not replace the current Genesis database: {error}"));
        }
    }

    if let Err(error) = fs::rename(&temporary, &database) {
        if let Some(safety_path) = &safety {
            let _ = fs::copy(safety_path, &database);
        }
        cleanup_pending(app_data);
        return Err(format!("Restore replacement failed; the safety copy was restored: {error}"));
    }

    remove_journals(&database);
    cleanup_pending(app_data);
    Ok(safety)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(label: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "genesis-storage-test-{label}-{}-{}",
            std::process::id(),
            timestamp()
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn write_sqlite_like(path: &Path, tail: &[u8]) {
        let mut bytes = SQLITE_HEADER.to_vec();
        bytes.extend_from_slice(tail);
        fs::write(path, bytes).unwrap();
    }

    #[test]
    fn pending_restore_replaces_database_and_keeps_safety_copy() {
        let dir = temp_dir("replace");
        let database = dir.join("genesis.db");
        write_sqlite_like(&database, b"old");
        write_sqlite_like(&dir.join(PENDING_DATABASE), b"new");
        fs::write(
            dir.join(PENDING_MANIFEST),
            r#"{"schemaVersion":1}"#,
        )
        .unwrap();

        let safety = apply_pending_restore(&dir).unwrap().unwrap();
        assert_eq!(fs::read(&database).unwrap(), [SQLITE_HEADER.as_slice(), b"new"].concat());
        assert_eq!(fs::read(&safety).unwrap(), [SQLITE_HEADER.as_slice(), b"old"].concat());
        assert!(!dir.join(PENDING_DATABASE).exists());
        assert!(!dir.join(PENDING_MANIFEST).exists());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn incompatible_restore_is_discarded_without_touching_database() {
        let dir = temp_dir("future");
        let database = dir.join("genesis.db");
        write_sqlite_like(&database, b"current");
        write_sqlite_like(&dir.join(PENDING_DATABASE), b"future");
        fs::write(
            dir.join(PENDING_MANIFEST),
            r#"{"schemaVersion":999}"#,
        )
        .unwrap();

        assert!(apply_pending_restore(&dir).is_err());
        assert_eq!(fs::read(&database).unwrap(), [SQLITE_HEADER.as_slice(), b"current"].concat());
        assert!(!dir.join(PENDING_DATABASE).exists());
        assert!(!dir.join(PENDING_MANIFEST).exists());
        fs::remove_dir_all(dir).unwrap();
    }
}
