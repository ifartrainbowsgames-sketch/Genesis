use std::{
    env,
    fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::Duration,
};

use keyring::Entry;
use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

const KEYRING_SERVICE: &str = "Genesis AI";
const DEFAULT_OLLAMA_MODEL: &str = "qwen3:8b";
const EMBEDDING_MODEL: &str = "nomic-embed-text";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SetupConfig {
    pub complete: bool,
    pub provider: String,
    pub model: String,
    #[serde(default)]
    pub workspace: Option<String>,
}

impl Default for SetupConfig {
    fn default() -> Self {
        Self {
            complete: false,
            provider: "ollama".into(),
            model: DEFAULT_OLLAMA_MODEL.into(),
            workspace: None,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SetupStatus {
    pub complete: bool,
    pub installer_mode: bool,
    pub provider: String,
    pub model: String,
    pub workspace: Option<String>,
    pub ollama_installed: bool,
    pub ollama_running: bool,
    pub embedding_model: String,
}

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("setup.json"))
}

pub fn load_config(app: &AppHandle) -> SetupConfig {
    config_path(app)
        .ok()
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

fn save_config(app: &AppHandle, config: &SetupConfig) -> Result<(), String> {
    let path = config_path(app)?;
    let payload = serde_json::to_vec_pretty(config).map_err(|e| e.to_string())?;
    fs::write(path, payload).map_err(|e| e.to_string())
}

pub fn installer_mode() -> bool {
    env::args().any(|arg| arg == "--installer-setup")
}

fn key_entry(provider: &str) -> Result<Entry, String> {
    Entry::new(KEYRING_SERVICE, provider).map_err(|e| format!("Credential store unavailable: {e}"))
}

pub fn load_secret(provider: &str) -> Option<String> {
    key_entry(provider).ok()?.get_password().ok()
}

fn save_secret(provider: &str, value: &str) -> Result<(), String> {
    key_entry(provider)?
        .set_password(value)
        .map_err(|e| format!("Could not store API key securely: {e}"))
}

fn common_ollama_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(local) = env::var("LOCALAPPDATA") {
        paths.push(Path::new(&local).join("Programs").join("Ollama").join("ollama.exe"));
        paths.push(Path::new(&local).join("Ollama").join("ollama.exe"));
    }
    paths
}

fn find_ollama() -> Option<PathBuf> {
    if let Ok(output) = Command::new("where").arg("ollama").output() {
        if output.status.success() {
            if let Some(first) = String::from_utf8_lossy(&output.stdout).lines().next() {
                let path = PathBuf::from(first.trim());
                if path.is_file() {
                    return Some(path);
                }
            }
        }
    }
    common_ollama_paths().into_iter().find(|path| path.is_file())
}

async fn ollama_running() -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
    {
        Ok(client) => client,
        Err(_) => return false,
    };
    client
        .get("http://127.0.0.1:11434/api/tags")
        .send()
        .await
        .map(|response| response.status().is_success())
        .unwrap_or(false)
}

fn install_ollama_with_winget() -> Result<(), String> {
    let output = Command::new("winget")
        .args([
            "install",
            "--id",
            "Ollama.Ollama",
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("winget unavailable: {e}"))?;
    if output.status.success() {
        Ok(())
    } else {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        Err(format!("winget failed: {detail}"))
    }
}

fn install_ollama_from_official_signed_installer() -> Result<(), String> {
    let installer = env::temp_dir().join("Genesis-OllamaSetup.exe");
    let download_and_verify = r#"
$ErrorActionPreference = 'Stop'
Invoke-WebRequest -UseBasicParsing 'https://ollama.com/download/OllamaSetup.exe' -OutFile $env:GENESIS_OLLAMA_INSTALLER
$sig = Get-AuthenticodeSignature -LiteralPath $env:GENESIS_OLLAMA_INSTALLER
if ($sig.Status -ne 'Valid') { throw ('Ollama installer signature is ' + $sig.Status) }
"#;
    let verified = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", download_and_verify])
        .env("GENESIS_OLLAMA_INSTALLER", &installer)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("Could not launch PowerShell for Ollama download: {e}"))?;
    if !verified.status.success() {
        let _ = fs::remove_file(&installer);
        let detail = String::from_utf8_lossy(&verified.stderr).trim().to_string();
        return Err(format!("Official Ollama installer verification failed: {detail}"));
    }

    let installed = Command::new(&installer)
        .args(["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("Could not run the verified Ollama installer: {e}"));
    let _ = fs::remove_file(&installer);
    match installed {
        Ok(status) if status.success() => Ok(()),
        Ok(status) => Err(format!("Verified Ollama installer exited with {status}")),
        Err(error) => Err(error),
    }
}

#[tauri::command]
pub async fn setup_status(app: AppHandle) -> SetupStatus {
    let config = load_config(&app);
    SetupStatus {
        complete: config.complete,
        installer_mode: installer_mode(),
        provider: config.provider,
        model: config.model,
        workspace: config.workspace,
        ollama_installed: find_ollama().is_some(),
        ollama_running: ollama_running().await,
        embedding_model: EMBEDDING_MODEL.into(),
    }
}

#[tauri::command]
pub fn setup_choose_workspace(app: AppHandle) -> Result<Option<String>, String> {
    let selected = FileDialog::new()
        .set_title("Choose a project folder for Genesis")
        .pick_folder();
    let Some(path) = selected else {
        return Ok(None);
    };
    if !path.is_dir() {
        return Err("Selected workspace is not a directory.".into());
    }
    let canonical = path.canonicalize().map_err(|e| format!("Could not open workspace: {e}"))?;
    let value = canonical.to_string_lossy().to_string();
    let mut config = load_config(&app);
    config.workspace = Some(value.clone());
    save_config(&app, &config)?;
    Ok(Some(value))
}

#[tauri::command]
pub async fn setup_install_ollama() -> Result<String, String> {
    if let Some(path) = find_ollama() {
        return Ok(format!("Ollama is already installed at {}", path.display()));
    }

    let result = tauri::async_runtime::spawn_blocking(|| {
        install_ollama_with_winget().or_else(|winget_error| {
            eprintln!("[genesis-setup] {winget_error}; trying the official signed installer");
            install_ollama_from_official_signed_installer()
        })
    })
    .await
    .map_err(|e| e.to_string())?;
    result?;

    for _ in 0..20 {
        if let Some(path) = find_ollama() {
            return Ok(format!("Ollama installed successfully at {}", path.display()));
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    Err("Ollama installation completed, but Genesis could not locate ollama.exe yet. Relaunch Genesis Setup to retry detection.".into())
}

#[tauri::command]
pub async fn setup_start_ollama() -> Result<String, String> {
    if ollama_running().await {
        return Ok("Ollama is already running.".into());
    }
    let exe = find_ollama().ok_or_else(|| "Ollama is not installed.".to_string())?;
    Command::new(exe)
        .arg("serve")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Could not start Ollama: {e}"))?;

    for _ in 0..30 {
        if ollama_running().await {
            return Ok("Ollama is running.".into());
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    Err("Ollama did not become ready within 15 seconds.".into())
}

fn valid_model_name(model: &str) -> bool {
    !model.is_empty()
        && model.len() <= 120
        && model
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, ':' | '-' | '_' | '.' | '/'))
}

#[tauri::command]
pub async fn setup_pull_model(model: String) -> Result<String, String> {
    if !valid_model_name(&model) {
        return Err("Invalid Ollama model name.".into());
    }
    let exe = find_ollama().ok_or_else(|| "Ollama is not installed.".to_string())?;
    let requested = vec![model.clone(), EMBEDDING_MODEL.to_string()];

    for name in requested {
        let exe = exe.clone();
        let name_for_command = name.clone();
        let output = tauri::async_runtime::spawn_blocking(move || {
            Command::new(exe)
                .args(["pull", &name_for_command])
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .output()
        })
        .await
        .map_err(|e| e.to_string())?
        .map_err(|e| format!("Could not run Ollama: {e}"))?;
        if !output.status.success() {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(format!("Could not pull {name}: {detail}"));
        }
    }
    Ok(format!("{model} and {EMBEDDING_MODEL} are ready."))
}

#[tauri::command]
pub async fn setup_validate_cloud(provider: String, api_key: String) -> Result<String, String> {
    let key = api_key.trim();
    if key.len() < 12 {
        return Err("API key is too short.".into());
    }
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let response = match provider.as_str() {
        "openai" => client
            .get("https://api.openai.com/v1/models")
            .bearer_auth(key)
            .send()
            .await
            .map_err(|e| format!("OpenAI validation failed: {e}"))?,
        "anthropic" => client
            .get("https://api.anthropic.com/v1/models")
            .header("x-api-key", key)
            .header("anthropic-version", "2023-06-01")
            .send()
            .await
            .map_err(|e| format!("Anthropic validation failed: {e}"))?,
        _ => return Err("Unsupported cloud provider.".into()),
    };

    if !response.status().is_success() {
        return Err(format!("The {provider} API rejected this key (HTTP {}).", response.status()));
    }
    save_secret(&provider, key)?;
    Ok(format!("{provider} API key validated and stored in the OS credential vault."))
}

#[tauri::command]
pub fn setup_save(app: AppHandle, provider: String, model: String) -> Result<SetupConfig, String> {
    if !matches!(provider.as_str(), "ollama" | "openai" | "anthropic") {
        return Err("Unsupported provider.".into());
    }
    if model.trim().is_empty() || model.len() > 200 {
        return Err("Model is required.".into());
    }
    let previous = load_config(&app);
    let config = SetupConfig {
        complete: true,
        provider,
        model: model.trim().to_string(),
        workspace: previous.workspace,
    };
    save_config(&app, &config)?;
    Ok(config)
}

#[tauri::command]
pub fn setup_finish(app: AppHandle) -> Result<(), String> {
    if !load_config(&app).complete {
        return Err("Setup has not been completed.".into());
    }

    if installer_mode() {
        app.exit(0);
        return Ok(());
    }

    let exe = env::current_exe().map_err(|e| e.to_string())?;
    Command::new(exe)
        .spawn()
        .map_err(|e| format!("Could not restart Genesis: {e}"))?;
    app.exit(0);
    Ok(())
}
