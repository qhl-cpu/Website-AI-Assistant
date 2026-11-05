# Automatically deploy the backend from GitHub

The local workflow `.github/workflows/deploy-backend.yml` targets
`qhl-cpu/Website-AI-Assistant` and these existing Azure resources:

| Resource | Value |
| --- | --- |
| Branch | `main` |
| Subscription | `13e73319-a03c-4064-9b86-0e68111e381c` |
| Resource group | `vl-rag-rg` |
| Container registry | `vlragregistry20261104` |
| Container App | `vancouver-laser-api` |

Pushing backend changes to `main` builds a `linux/amd64` image on a GitHub-hosted
runner, runs the backend tests inside that image with placeholder credentials,
pushes the tested image to ACR, and updates the Container App. It uses Docker
build/push rather than ACR Tasks. Each image is tagged with the full commit SHA.

Only changes to `vl-rag-assistant/backend/**` or the workflow itself trigger an
automatic deployment. You can also select **Actions → Deploy backend to Azure →
Run workflow**, choosing `main`. Other branches cannot deploy through this
workflow. Deployments are serialized rather than interrupted midway through an
Azure update.

## 1. Configure Azure's trust in GitHub once

These commands change Azure identity/role settings when you run them. They have
not been executed as part of preparing these files. Use an Azure account with
permission to create managed identities and assign roles, such as an Owner for
this resource group. Run the blocks below in the same Bash or Zsh terminal,
continuing only after each succeeds.

Sign in and select the existing subscription:

```sh
az login
az account set --subscription 13e73319-a03c-4064-9b86-0e68111e381c

VL_DEPLOY_IDENTITY=github-vl-rag-deploy
VL_RESOURCE_GROUP=vl-rag-rg
```

Create a deployment identity (separate from the Container App's runtime identity):

```sh
az identity create --name "$VL_DEPLOY_IDENTITY" --resource-group "$VL_RESOURCE_GROUP" --location westus2

VL_DEPLOY_PRINCIPAL_ID=$(az identity show --name "$VL_DEPLOY_IDENTITY" --resource-group "$VL_RESOURCE_GROUP" --query principalId --output tsv)
```

Trust tokens issued specifically to this repository's `main` branch:

```sh
az identity federated-credential create \
  --name github-main \
  --identity-name "$VL_DEPLOY_IDENTITY" \
  --resource-group "$VL_RESOURCE_GROUP" \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:qhl-cpu/Website-AI-Assistant:ref:refs/heads/main \
  --audiences api://AzureADTokenExchange
```

Grant the deployment identity permission to update Container Apps within this
resource group, read this registry's configuration, and push/pull its images:

```sh
VL_GROUP_ID=$(az group show --name "$VL_RESOURCE_GROUP" --query id --output tsv)
VL_REGISTRY_ID=$(az acr show --name vlragregistry20261104 --resource-group "$VL_RESOURCE_GROUP" --query id --output tsv)

az role assignment create --assignee-object-id "$VL_DEPLOY_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Container Apps Contributor" --scope "$VL_GROUP_ID" --output none

az role assignment create --assignee-object-id "$VL_DEPLOY_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role Reader --scope "$VL_REGISTRY_ID" --output none

az role assignment create --assignee-object-id "$VL_DEPLOY_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role AcrPush --scope "$VL_REGISTRY_ID" --output none
```

The registry currently uses `LegacyRegistryPermissions`, so `AcrPush` is
appropriate. If you later switch it to RBAC + ABAC repository permissions, review
the ACR role assignments; that mode uses roles such as **Container Registry
Repository Writer** instead. This setup does not change the existing Container
App credentials used to pull its runtime image.

## 2. Add three GitHub Actions repository secrets

Open [the repository's Actions secrets settings](https://github.com/qhl-cpu/Website-AI-Assistant/settings/secrets/actions).
Choose **New repository secret** for each item below. Obtain its value with the
listed command in the same terminal:

| Secret name | Command to display its value |
| --- | --- |
| `AZURE_CLIENT_ID` | `az identity show --name "$VL_DEPLOY_IDENTITY" --resource-group "$VL_RESOURCE_GROUP" --query clientId --output tsv` |
| `AZURE_TENANT_ID` | `az account show --query tenantId --output tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id --output tsv` |

These are identifiers, not passwords. OIDC obtains a short-lived Azure token for
each eligible workflow run. No Azure client secret or ACR admin password is
needed. Do not configure `auth-type: IDENTITY` or a GitHub deployment environment
on this job: this configuration uses OIDC with a branch-scoped trust subject,
not the VM identity login mode or an environment-scoped trust subject.

The production OpenAI and Qdrant keys remain in the Azure Container App's existing
environment/secret settings. They are not required in GitHub; automated tests use
mocks and placeholder credentials.

## 3. Enable the workflow by committing and pushing it

After completing the identity setup and GitHub secrets, commit and push the
workflow to `main` yourself. Its first push will trigger deployment because the
workflow file is included in its path filters. Until you push it, these local
files do not enable automatic deployment. If GitHub prompts you to enable
Actions for the repository, enable it in the repository's Actions settings.

Watch [Actions](https://github.com/qhl-cpu/Website-AI-Assistant/actions) for
**Deploy backend to Azure**. The workflow waits for the new ready revision in
Single revision mode, then checks `/health` and `/ready` without making paid
chat requests. Its run summary shows the deployed image, revision, and URL.
Confirm the new behavior in the website chat UI after a successful run.

If post-deployment endpoint checks fail, the run fails and prints the error;
it does not automatically roll back an image that Azure has already activated.
Review the Container App's console logs and revision status before retrying.
If the app is changed to Multiple revision mode, the workflow stops before
updating it so traffic routing can be reviewed.

## Troubleshooting

- **Missing repository Actions secret:** check all three names in step 2.
- **No matching federated identity record:** verify the repository owner/name,
  `main` branch, issuer, and audience match the credential exactly. A renamed
  repository needs a matching credential update.
- **AuthorizationFailed / denied push:** check the three role assignments above;
  new identity trust and permissions may need time to propagate.
- **Image pull fails in Azure:** the workflow's push identity and the Container
  App's image-pull identity are separate. Check the existing runtime registry
  authentication in the Container App.

This workflow updates the Python backend only. WordPress UI snippets and Qdrant
knowledge ingestion remain separate update processes.

## Official references

- [Azure Login with OIDC](https://github.com/Azure/login#login-with-openid-connect-oidc-recommended)
- [Federated credentials for managed identities](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust-user-assigned-managed-identity)
- [ACR roles and permission modes](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-built-in-roles-overview)
- [Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
