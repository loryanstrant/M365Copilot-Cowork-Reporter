# Deploying the M365 Copilot Cowork Reporter

Two supported paths: the **one-click button** (uses prebuilt public images) and **azd** (builds
from source). Both provision the same shape — PostgreSQL flexible server, a Container Apps
environment, and the `api` + `worker` container apps.

## 1. One-click button

### For end users

1. Select **Deploy to Azure** in the README.
2. Choose a subscription, a resource group and a region.
3. Enter an **admin password**. This becomes the dashboard password for the `admin` user. The
   database password and the Fernet encryption key are generated for you.
4. Optionally open the **Authentication** tab to enable Entra ID single sign-on at deploy time.
5. When the deployment completes, open the deployment's **Outputs** and copy **`dashboardUrl`**.

Sign in with `admin` (or the admin username you set) and the password you chose, then complete
**Settings** to connect your tenant.

### Choosing a region and database size

Pick a region close to your users and to the subscriptions you're reporting cost on. The default
PostgreSQL SKU is the smallest burstable tier, which is ample for a single tenant — audit events
are the largest table and compress well. Scale up in the portal later if backfill is slow.

### For maintainers (one-time, so the button works for everyone)

The button pulls **public** images from GitHub Container Registry. After the first successful run
of the **Publish container images** workflow:

1. Open the repo's **Packages**.
2. For both `m365copilot-cowork-reporter/api` and `.../worker`, open **Package settings** and set
   visibility to **Public**.

Container Apps pulls anonymously, so private packages cause the deployment to fail with an image
pull error.

## 2. azd (build from source)

```powershell
azd auth login

# Provide the secrets azd will pass to Bicep
azd env set POSTGRES_ADMIN_PASSWORD "<strong-password>"
azd env set ADMIN_PASSWORD "<admin-password>"
azd env set FERNET_KEY "$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

azd up
```

`azd up` provisions the infrastructure and builds and pushes the images from source, so no public
packages are needed. Use this when you've modified the code.

## After deployment

1. Open `dashboardUrl` and sign in.
2. **Settings** → run the guided wizard to create the Entra app registration
   (`AuditLogsQuery.Read.All`, `User.Read.All`, admin-consented) and assign **Cost Management
   Reader** on each subscription in scope.
3. Paste Tenant ID, Client ID and Client secret → **Test connection**.
4. **Run now** to pull audit, directory and cost.
5. **Upload CSV** for the two admin-centre exports that have no API.
6. **Settings → Historical audit backfill** for history back to Cowork GA.

To evaluate without a tenant connection, use **Settings → Demo data → Load demo data**, then
**Clear demo data** before your first live run.

## Entra single sign-on (optional)

The dashboard is protected by the admin password by default. Easy Auth adds read-only viewer
sign-in with work accounts while administration stays behind the password.

**Prerequisite:** an Entra app registration for sign-in (you can reuse the reporter's own). Note its
**Application (client) ID** and create a **client secret**. After deployment, add the redirect URI
`https://<your-dashboardUrl>/.auth/login/aad/callback` under **Authentication → Web**. To restrict
viewers to a security group, also add a **groups** claim under **Token configuration**.

**At deploy time:** on the Deploy to Azure form, open the **Authentication** tab, set **Enable Entra
ID single sign-on = Yes**, and paste the client ID, client secret and (optionally) tenant ID.

**After deployment:** open the `…-api-…` Container App → **Settings → Authentication** → **Add
identity provider** → **Microsoft**, use the client ID and secret, and set *unauthenticated
requests* to **Allow**.

Once enabled, the sign-in page shows a **Sign in with Microsoft** button and returning users are
signed in silently.

## Updating a deployment

- **Button deployments** track the published image tags. Re-run the deployment, or update the image
  tag on both container apps, to pick up a new release.
- **azd deployments**: `azd deploy` rebuilds and pushes from source without re-provisioning
  infrastructure.

Database migrations run automatically on API startup, so no manual Alembic step is needed.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Deployment fails pulling an image | GHCR packages are still private — see the maintainer step above. |
| No audit events after a run | The legacy `AuditLog.Read.All` was granted instead of `AuditLogsQuery.Read.All`. |
| Cost is empty | `Cost Management Reader` isn't assigned to the app registration on that subscription. |
| Sign-in fails after deploy | The admin password contains characters that were mangled in the portal form — reset it on the container app's secrets. |
