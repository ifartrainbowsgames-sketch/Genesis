use std::{
    env,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::Duration,
};

use serde::{Deserialize, Serialize};

const OLLAMA_API: &str = "http://127.0.0.1:11434";
const EMBEDDING_MODEL: &str = "nomic-embed-text";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OllamaProbe {
    pub installed: bool,
    pub running: bool,
    pub path: Option<String>,
    pub models: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct TagsResponse {
    #[serde(default)]
    models: Vec<TagModel>,
}

#[derive(Debug, Deserialize)]
struct TagModel {
    name: String,
    #[serde(default)]
    model: Option<String>,
}

fn push_candidate(paths: &mut Vec<PathBuf>, value: PathBuf) {
    if !paths.iter().any(|item| item == &value) {
        paths.push(value);
    }
}

fn common_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();

    if let Ok(local) = env::var("LOCALAPPDATA") {
        push_candidate(&mut paths, Path::new(&local).join("Programs").join("Ollama").join("ollama.exe"));
        push_candidate(&mut paths, Path::new(&local).join("Ollama").join("ollama.exe"));
    }

    for variable in ["PROGRAMFILES", "ProgramW6432", "PROGRAMFILES(X86)"] {
        if let Ok(root) = env::var(variable) {
            push_candidate(&mut paths, Path::new(&root).join("Ollama").join("ollama.exe"));
            push_candidate(&mut paths, Path::new(&root).join("Ollama Inc").join("Ollama").join("ollama.exe"));
        }
    }

    paths
}

pub fn find_ollama() -> Option<PathBuf> {
    if let Ok(output) = Command::new("where").arg("ollama").output() {
        if output.status.success() {
            for line in String::from_utf8_lossy(&output.stdout).lines() {
                let path = PathBuf::from(line.trim());
                if path.is_file() {
                    return Some(path);
                }
            }
        }
    }

    common_paths().into_iter().find(|path| path.is_file())
}

async fn tags() -> Result<Vec<String>, String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .map_err(|error| error.to_string())?;
    let response = client
        .get(format!("{OLLAMA_API}/api/tags"))
        .send()
        .await
        .map_err(|error| format!("Ollama is not responding: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("Ollama returned HTTP {}", response.status()));
    }
    let payload = response
        .json::<TagsResponse>()
        .await
        .map_err(|error| format!("Could not read Ollama model list: {error}"))?;
    let mut names = Vec::new();
    for item in payload.models {
        if !names.iter().any(|name| name.eq_ignore_ascii_case(&item.name)) {
            names.push(item.name);
        }
        if let Some(model) = item.model {
            if !names.iter().any(|name| name.eq_ignore_ascii_case(&model)) {
                names.push(model);
            }
        }
    }
    names.sort_by_key(|name| name.to_ascii_lowercase());
    Ok(names)
}

fn has_model(models: &[String], requested: &str) -> bool {
    models.iter().any(|item| item.eq_ignore_ascii_case(requested))
}

fn valid_model_name(model: &str) -> bool {
    !model.is_empty()
        && model.len() <= 120
        && model
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, ':' | '-' | '_' | '.' | '/'))
}

async fn running() -> bool {
    tags().await.is_ok()
}

#[tauri::command]
pub async fn setup_ollama_probe() -> OllamaProbe {
    let path = find_ollama();
    let models = tags().await.unwrap_or_default();
    OllamaProbe {
        installed: path.is_some(),
        running: !models.is_empty() || running().await,
        path: path.map(|value| value.to_string_lossy().to_string()),
        models,
    }
}

#[tauri::command]
pub async fn setup_ollama_start_existing() -> Result<String, String> {
    if running().await {
        return Ok("Ollama is already running.".into());
    }
    let exe = find_ollama().ok_or_else(|| "Ollama is not installed in PATH, LocalAppData, or Program Files.".to_string())?;
    Command::new(&exe)
        .arg("serve")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Could not start {}: {error}", exe.display()))?;

    for _ in 0..30 {
        if running().await {
            return Ok(format!("Ollama is running from {}", exe.display()));
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    Err("Ollama did not become ready within 15 seconds.".into())
}

#[tauri::command]
pub async fn setup_ollama_prepare_models(model: String) -> Result<String, String> {
    if !valid_model_name(&model) {
        return Err("Invalid Ollama model name.".into());
    }
    if !running().await {
        return Err("Ollama is installed but its local API is not running.".into());
    }
    let exe = find_ollama().ok_or_else(|| "Genesis cannot locate ollama.exe.".to_string())?;
    let requested = [model.clone(), EMBEDDING_MODEL.to_string()];
    let mut installed = tags().await?;
    let mut messages = Vec::new();

    for name in requested {
        if has_model(&installed, &name) {
            messages.push(format!("{name} already installed — skipped download."));
            continue;
        }

        let command_exe = exe.clone();
        let command_name = name.clone();
        let output = tauri::async_runtime::spawn_blocking(move || {
            Command::new(command_exe)
                .args(["pull", &command_name])
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .output()
        })
        .await
        .map_err(|error| error.to_string())?
        .map_err(|error| format!("Could not run Ollama: {error}"))?;

        if !output.status.success() {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(format!("Could not pull {name}: {detail}"));
        }
        messages.push(format!("{name} downloaded and verified by Ollama."));
        installed = tags().await.unwrap_or(installed);
    }

    Ok(messages.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_model_match_is_case_insensitive() {
        let models = vec!["qwen3:8b".to_string(), "nomic-embed-text:latest".to_string()];
        assert!(has_model(&models, "QWEN3:8B"));
        assert!(!has_model(&models, "qwen3:4b"));
    }

    #[test]
    fn model_names_reject_shell_syntax() {
        assert!(valid_model_name("qwen3:8b"));
        assert!(valid_model_name("registry/model:latest"));
        assert!(!valid_model_name("qwen3:8b && calc.exe"));
    }
}
