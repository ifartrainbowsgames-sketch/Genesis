use std::{fs, path::PathBuf};

use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

mod setup;

fn starter_workspace(default_workspace: &PathBuf) -> std::io::Result<()> {
    fs::create_dir_all(default_workspace)?;
    let empty = fs::read_dir(default_workspace)?.next().is_none();
    if empty {
        fs::write(
            default_workspace.join("README.md"),
            "# Welcome to Genesis\n\nThis is your starter workspace.\n\nUse **Ask Genesis** in the Workbench to inspect, plan, and propose changes. Generated changes still require explicit approval before they are applied.\n",
        )?;
    }
    Ok(())
}

fn sqlite_database_url(path: &PathBuf) -> String {
    format!(
        "sqlite+aiosqlite:///{}",
        path.to_string_lossy().replace('\\', "/")
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            setup::setup_status,
            setup::setup_choose_workspace,
            setup::setup_install_ollama,
            setup::setup_start_ollama,
            setup::setup_pull_model,
            setup::setup_validate_cloud,
            setup::setup_save,
            setup::setup_finish,
        ])
        .setup(|app| {
            #[cfg(desktop)]
            {
                let app_data = app.path().app_local_data_dir()?;
                let default_workspace = app_data.join("workspace");
                let database_path = app_data.join("genesis.db");
                let database_url = sqlite_database_url(&database_path);
                starter_workspace(&default_workspace)?;

                let config = setup::load_config(app.handle());
                let installer_mode = setup::installer_mode();

                // Upgrades should not force an already-configured user through setup again.
                if installer_mode && config.complete {
                    app.handle().exit(0);
                    return Ok(());
                }

                if config.complete && !installer_mode {
                    let configured_workspace = config
                        .workspace
                        .as_ref()
                        .map(PathBuf::from)
                        .filter(|path| path.is_dir())
                        .unwrap_or_else(|| default_workspace.clone());

                    let mut sidecar = app
                        .shell()
                        .sidecar("genesis-server")?
                        .env("WORKSPACE_ROOT", configured_workspace.as_os_str())
                        .env("DATABASE_URL", &database_url)
                        .env("SERVER_HOST", "127.0.0.1")
                        .env("WEB_ORIGIN", "http://tauri.localhost")
                        .env("GENESIS_DEFAULT_PROVIDER", &config.provider);

                    match config.provider.as_str() {
                        "ollama" => {
                            sidecar = sidecar.env("OLLAMA_CHAT_MODEL", &config.model);
                        }
                        "openai" => {
                            sidecar = sidecar.env("OPENAI_MODEL", &config.model);
                            if let Some(secret) = setup::load_secret("openai") {
                                sidecar = sidecar.env("OPENAI_API_KEY", secret);
                            }
                        }
                        "anthropic" => {
                            sidecar = sidecar.env("ANTHROPIC_MODEL", &config.model);
                            if let Some(secret) = setup::load_secret("anthropic") {
                                sidecar = sidecar.env("ANTHROPIC_API_KEY", secret);
                            }
                        }
                        _ => {}
                    }

                    let (mut events, child) = sidecar.spawn()?;
                    tauri::async_runtime::spawn(async move {
                        let _child = child;
                        while let Some(event) = events.recv().await {
                            match event {
                                CommandEvent::Stdout(bytes) => {
                                    println!("[genesis-server] {}", String::from_utf8_lossy(&bytes));
                                }
                                CommandEvent::Stderr(bytes) => {
                                    eprintln!("[genesis-server] {}", String::from_utf8_lossy(&bytes));
                                }
                                _ => {}
                            }
                        }
                    });
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Genesis");
}
