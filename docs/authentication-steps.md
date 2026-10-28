# Factory authentication setup

## 1. Connect to the host
On your computer, connect; then switch to factory in the host session:
```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1
aws ssm start-session --target i-0949d809e65004a73
# In the host session:
sudo -iu factory
umask 077
. "$HOME/.config/software-factory/deployment.env"
```
## 2. Enroll the GitHub App
Paste the downloaded private key **into the terminal, not chat**, in a session where input is not recorded:
```sh
cat > "$HOME/.config/software-factory/github-app.pem"
# Paste the key, then press Ctrl-D.
```
Replace both placeholders below with numeric IDs. The documented `factory-example` IDs are `5430144` and `174237987`.
```sh
cat > "$HOME/.config/software-factory/github-app.json" <<'EOF'
{"app_id": YOUR_APP_ID, "installation_id": YOUR_INSTALLATION_ID}
EOF
chmod 600 "$HOME/.config/software-factory/github-app.pem" "$HOME/.config/software-factory/github-app.json"
```
## 3. Enroll Copilot
As factory, start an authentication-only container:
```sh
install -d -m 0700 "$HOME/.pi/agent"
docker run --rm -it --pull=never --platform linux/arm64 \
  --mount "type=bind,src=$HOME/.pi/agent,dst=/home/factory/.pi/agent" --entrypoint sh "$RUNNER_IMAGE"
```
Inside the container, run Pi, enter `/login`, select GitHub Copilot, and complete browser authorization. Exit Pi, then check and exit the container:
```sh
pi --no-extensions --no-mcp --no-skills --no-context-files --no-session
chmod 700 "$HOME/.pi/agent"; chmod 600 "$HOME/.pi/agent/auth.json"
pi auth check --provider github-copilot --no-extensions --no-mcp --no-context-files
exit
```
## 4. Create factory configuration
Back in the host's factory shell, replace the repository and model with your intended values:
```sh
cat > "$HOME/.config/software-factory/factory.toml" <<EOF
repository = "OWNER/REPOSITORY"
model = "YOUR_COPILOT_MODEL_ID"
agent_image = "$AGENT_IMAGE"
EOF
chmod 600 "$HOME/.config/software-factory/factory.toml"
```
