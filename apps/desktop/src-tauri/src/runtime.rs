use std::{net::TcpListener, sync::Mutex};

use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::process::CommandChild;

use crate::setup;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeInfo {
    pub api_base: String,
    pub api_token: String,
    pub port: u16,
}

impl RuntimeInfo {
    pub fn allocate() -> Result<Self, String> {
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .map_err(|error| format!("Could not reserve a local Genesis API port: {error}"))?;
        let port = listener
            .local_addr()
            .map_err(|error| format!("Could not read the reserved Genesis API port: {error}"))?
            .port();
        drop(listener);

        let mut random = [0_u8; 32];
        getrandom::fill(&mut random)
            .map_err(|error| format!("Could not create a private Genesis API token: {error}"))?;
        let api_token = random.iter().map(|byte| format!("{byte:02x}")).collect();

        Ok(Self {
            api_base: format!("http://127.0.0.1:{port}"),
            api_token,
            port,
        })
    }
}

#[derive(Default)]
pub struct SidecarState(pub Mutex<Option<CommandChild>>);

pub fn store_sidecar(state: State<'_, SidecarState>, child: CommandChild) -> Result<(), String> {
    let mut slot = state
        .0
        .lock()
        .map_err(|_| "Genesis sidecar state lock was poisoned".to_string())?;
    if let Some(previous) = slot.take() {
        let _ = previous.kill();
    }
    *slot = Some(child);
    Ok(())
}

pub fn clear_sidecar(state: State<'_, SidecarState>) {
    if let Ok(mut slot) = state.0.lock() {
        slot.take();
    }
}

pub fn stop_sidecar(app: &AppHandle) {
    if let Ok(mut slot) = app.state::<SidecarState>().0.lock() {
        if let Some(child) = slot.take() {
            let _ = child.kill();
        }
    }
}

#[tauri::command]
pub fn runtime_info(state: State<'_, RuntimeInfo>) -> RuntimeInfo {
    state.inner().clone()
}

#[tauri::command]
pub fn setup_finish(app: AppHandle) -> Result<(), String> {
    if !setup::load_config(&app).complete {
        return Err("Setup has not been completed.".into());
    }

    if setup::installer_mode() {
        app.exit(0);
    } else {
        // Tauri's managed restart sends the normal exit events first, which gives Genesis
        // a chance to stop the sidecar cleanly before the replacement process starts.
        app.request_restart();
    }
    Ok(())
}
