use std::{env, fs, path::PathBuf, time::Duration};

use keyring::Entry;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

const KEYRING_SERVICE: &str = "Genesis AI";
const EMBEDDING_MODEL: &str = "nomic-embed-text";

#[derive(Debug, Deserialize)]
struct SetupConfig {
    complete: bool,
    provider: String,
    model: String,
    workspace: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VerificationCheck {
    pub name: String,
    pub status: String,
    pub detail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SetupVerification {
    pub ready: bool,
    pub checks: Vec<VerificationCheck>,
}

fn check(name: &str, ready: bool, detail: impl Into<String>) -> VerificationCheck {
    VerificationCheck {
        name: name.into(),
        status: if ready { "ready" } else { "failed" }.into(),
        detail: detail.into(),
    }
}

fn load_config(app: &AppHandle) -> Result<SetupConfig, String> {
    let path = app
        .path()
        .app_local_data_dir()
        .map_err(|e| e.to_string())?
        .join("setup.json");
    let text = fs::read_to_string(path).map_err(|e| format!("Could not read setup.json: {e}"))?;
    serde_json::from_str(&text).map_err(|e| format!("Could not parse setup.json: {e}"))
}

fn app_data_probe(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| format!("Could not create Genesis app-data directory: {e}"))?;
    let probe = dir.join(format!(".genesis-write-probe-{}", std::process::id()));
    fs::write(&probe, b"ok").map_err(|e| format!("Genesis app-data is not writable: {e}"))?;
    fs::remove_file(&probe).map_err(|e| format!("Could not clean up Genesis app-data probe: {e}"))?;
    Ok(dir)
}

fn configured_workspace(app_data: &PathBuf, config: &SetupConfig) -> PathBuf {
    config
        .workspace
        .as_ref()
        .map(PathBuf::from)
        .filter(|path| path.is_dir())
        .unwrap_or_else(|| app_data.join("workspace"))
}

fn secure_secret_exists(provider: &str) -> bool {
    Entry::new(KEYRING_SERVICE, provider)
        .ok()
        .and_then(|entry| entry.get_password().ok())
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
}

async fn ollama_models() -> Result<Vec<String>, String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(4))
        .build()
        .map_err(|e| e.to_string())?;
    let response = client
        .get("http://127.0.0.1:11434/api/tags")
        .send()
        .await
        .map_err(|e| format!("Ollama is not responding: {e}"))?;
    if !response.status().is_success() {
        return Err(format!("Ollama returned HTTP {}", response.status()));
    }
    let payload: serde_json::Value = response.json().await.map_err(|e| e.to_string())?;
    let models = payload
        .get("models")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
        .filter_map(|item| {
            item.get("name")
                .or_else(|| item.get("model"))
                .and_then(|value| value.as_str())
                .map(ToOwned::to_owned)
        })
        .collect();
    Ok(models)
}

fn model_present(installed: &[String], requested: &str) -> bool {
    installed.iter().any(|name| {
        name == requested
            || name.strip_suffix(":latest") == Some(requested)
            || requested.strip_suffix(":latest") == Some(name.as_str())
    })
}

#[tauri::command]
pub async fn setup_verify(app: AppHandle) -> SetupVerification {
    let mut checks = Vec::new();

    let app_data = match app_data_probe(&app) {
        Ok(path) => {
            checks.push(check("Genesis storage", true, "Application data is writable; the embedded database can be created here."));
            path
        }
        Err(error) => {
            checks.push(check("Genesis storage", false, error));
            return SetupVerification { ready: false, checks };
        }
    };

    let config = match load_config(&app) {
        Ok(config) if config.complete => {
            checks.push(check("Setup configuration", true, format!("{} / {} is selected.", config.provider, config.model)));
            config
        }
        Ok(_) => {
            checks.push(check("Setup configuration", false, "Choose and prepare an AI provider before finishing installation."));
            return SetupVerification { ready: false, checks };
        }
        Err(error) => {
            checks.push(check("Setup configuration", false, error));
            return SetupVerification { ready: false, checks };
        }
    };

    let workspace = configured_workspace(&app_data, &config);
    match fs::read_dir(&workspace) {
        Ok(_) => checks.push(check("Workspace", true, format!("{} is readable.", workspace.display()))),
        Err(error) => checks.push(check("Workspace", false, format!("Could not read {}: {error}", workspace.display()))),
    }

    match config.provider.as_str() {
        "ollama" => match ollama_models().await {
            Ok(models) => {
                let chat_ready = model_present(&models, &config.model);
                let embed_ready = model_present(&models, EMBEDDING_MODEL);
                checks.push(check(
                    "Local chat model",
                    chat_ready,
                    if chat_ready {
                        format!("{} is installed in Ollama.", config.model)
                    } else {
                        format!("{} is not installed yet.", config.model)
                    },
                ));
                checks.push(check(
                    "Memory embedding model",
                    embed_ready,
                    if embed_ready {
                        format!("{EMBEDDING_MODEL} is installed in Ollama.")
                    } else {
                        format!("{EMBEDDING_MODEL} is not installed yet.")
                    },
                ));
            }
            Err(error) => checks.push(check("Ollama service", false, error)),
        },
        "openai" | "anthropic" => {
            let secret_ready = secure_secret_exists(&config.provider);
            checks.push(check(
                "Secure API credential",
                secret_ready,
                if secret_ready {
                    format!("The {} credential is present in the Windows credential store.", config.provider)
                } else {
                    format!("The {} credential is missing from the Windows credential store.", config.provider)
                },
            ));
        }
        other => checks.push(check("AI provider", false, format!("Unsupported configured provider: {other}"))),
    }

    let ready = checks.iter().all(|item| item.status == "ready");
    SetupVerification { ready, checks }
}
