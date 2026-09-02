use std::fs;

use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            #[cfg(desktop)]
            {
                let app_data = app.path().app_local_data_dir()?;
                let workspace = app_data.join("workspace");
                fs::create_dir_all(&workspace)?;

                let sidecar = app
                    .shell()
                    .sidecar("genesis-server")?
                    .env("WORKSPACE_ROOT", workspace.as_os_str())
                    .env("SERVER_HOST", "127.0.0.1")
                    .env("WEB_ORIGIN", "http://tauri.localhost");
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
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Genesis");
}
