import Link from "next/link";
import styles from "../product-pages.module.css";

const SETTINGS = [
  { href: "/setup", title: "Models & provider", detail: "Local Ollama or cloud provider, model selection, workspace setup and installation repair." },
  { href: "/voice", title: "Voice", detail: "Speech language, transcription diagnostics and spoken-reply preferences. Everyday voice input lives in Workbench." },
  { href: "/connections", title: "Connections", detail: "MCP and external capability connections. Keep integrations modular instead of hard-wiring them into the Workbench." },
  { href: "/memory", title: "Memory", detail: "Inspect, search and manage local episodic and consolidated project knowledge." },
  { href: "/runtime", title: "Runtime", detail: "Workers, schedules and execution controls for advanced users." },
  { href: "/diagnostics", title: "Diagnostics & recovery", detail: "Health, database schema, backups, restore and installation repair." },
  { href: "/evolution", title: "Evolution", detail: "Review evaluation candidates and manually promote improvements. Never an automatic self-modification surface." },
  { href: "/research", title: "Research", detail: "Source-tracked research controls and advanced query options." },
  { href: "/workbench", title: "Developer workbench", detail: "Monaco editor, explorer, checks, Git diff and fixed-command terminal for users who want the full engineering surface." },
];

export default function SettingsPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Settings</h1>
          <p>Genesis keeps operational machinery here so the main Workbench stays focused on intent, work and results.</p>
        </div>
      </header>

      <section className={styles.grid}>
        {SETTINGS.map((item) => (
          <Link className={styles.settingLink} href={item.href} key={item.href}>
            <strong>{item.title}</strong>
            <span>{item.detail}</span>
          </Link>
        ))}
      </section>
    </main>
  );
}
