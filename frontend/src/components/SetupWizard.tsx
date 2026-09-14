import { useState, type ReactNode } from "react";
import {
  APP_DISPLAY_NAME,
  REQUIRED_AZURE_ROLE,
  REQUIRED_PERMISSIONS,
  SETUP_SCRIPT,
} from "../lib/setup";

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked — user can select manually */
        }
      }}
      className="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

function Perm({ value }: { value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
      <code className="text-xs text-slate-700 dark:text-slate-200">{value}</code>
      <CopyButton text={value} />
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h4>
        <div className="text-sm text-slate-600 dark:text-slate-300">{children}</div>
      </div>
    </div>
  );
}

/**
 * Guided first-run setup of the Entra app registration and Azure cost access the
 * reporter needs. Shown until a connection is configured. Collapsible so it stays
 * out of the way once you know the drill.
 */
export default function SetupWizard({ defaultOpen = true }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [showScript, setShowScript] = useState(false);

  return (
    <div className="card overflow-hidden border-brand-200 dark:border-brand-800/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 bg-brand-50 px-6 py-4 text-left dark:bg-brand-900/20"
      >
        <div>
          <h2 className="text-lg font-semibold text-brand-800 dark:text-brand-300">
            First-time setup: create your app registration
          </h2>
          <p className="mt-0.5 text-sm text-brand-700/80 dark:text-brand-400/80">
            The reporter reads Purview audit and Azure cost. Set up an Entra app
            registration once, then paste its details into the form below.
          </p>
        </div>
        <span className="shrink-0 text-brand-700 dark:text-brand-300">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="space-y-6 px-6 py-5">
          <Step n={1} title="Create the app registration">
            <p>
              Open{" "}
              <a
                href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-brand-600 underline dark:text-brand-400"
              >
                Entra → App registrations → New registration
              </a>
              . Name it <span className="font-medium">{APP_DISPLAY_NAME}</span>, leave the
              defaults, and select <span className="font-medium">Register</span>.
            </p>
          </Step>

          <Step n={2} title="Add Graph application permissions">
            <p className="mb-2">
              Under <span className="font-medium">API permissions → Add a permission →
              Microsoft Graph → Application permissions</span>, add these two, then choose{" "}
              <span className="font-medium">Grant admin consent</span>:
            </p>
            <div className="space-y-2">
              {REQUIRED_PERMISSIONS.map((p) => (
                <Perm key={p.value} value={p.value} />
              ))}
            </div>
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              Microsoft began enforcing <code>AuditLogsQuery.Read.All</code> in April 2026.
              The legacy <code>AuditLog.Read.All</code> silently returns zero Copilot
              records — make sure you grant the <em>Query</em> permission.
            </p>
          </Step>

          <Step n={3} title="Grant Azure cost access">
            <p className="mb-2">
              On each subscription you want spend for, open{" "}
              <span className="font-medium">Access control (IAM) → Add role assignment</span>{" "}
              and assign this role to the app registration:
            </p>
            <Perm value={REQUIRED_AZURE_ROLE.value} />
          </Step>

          <Step n={4} title="Create a client secret">
            <p>
              Under <span className="font-medium">Certificates &amp; secrets → New client
              secret</span>, create one and copy its <span className="font-medium">Value</span>{" "}
              immediately (it's shown only once).
            </p>
          </Step>

          <Step n={5} title="Copy the IDs and paste below">
            <p>
              From the app's <span className="font-medium">Overview</span> page, copy the{" "}
              <span className="font-medium">Directory (tenant) ID</span> and{" "}
              <span className="font-medium">Application (client) ID</span>. Paste those plus the
              secret into the form below, then <span className="font-medium">Save</span> and{" "}
              <span className="font-medium">Test connection</span>.
            </p>
          </Step>

          <div className="rounded-lg border border-slate-200 dark:border-slate-700">
            <button
              type="button"
              onClick={() => setShowScript((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-700 dark:text-slate-200"
            >
              <span>Prefer to script it? Run this instead of steps 1–4</span>
              <span className="text-slate-400">{showScript ? "▲" : "▼"}</span>
            </button>
            {showScript && (
              <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
                <div className="mb-2 flex justify-end">
                  <CopyButton text={SETUP_SCRIPT} label="Copy script" />
                </div>
                <pre className="max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
                  <code>{SETUP_SCRIPT}</code>
                </pre>
                <p className="mt-2 text-xs text-slate-400">
                  Resolves permission IDs by name, creates the app, grants consent, assigns
                  Cost Management Reader on every subscription, and prints the Tenant ID,
                  Client ID, and secret to paste below.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
