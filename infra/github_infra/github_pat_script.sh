#!/usr/bin/env bash
#
# create_github_pat.sh - GitHub PAT manager for repository secrets
#
# Uses `gh auth refresh` to obtain a scoped classic token via the gh CLI,
# caches it locally, and writes it to a Terraform .tfvars file.
#
# NOTE: GitHub has no API or CLI command to programmatically *create* a new
# PAT. The gh CLI's own authenticated token (obtained via gh auth refresh
# with explicit scopes) is the token we store and reuse.
#
# Usage: ./create_github_pat.sh -o <owner> -r <repo> [options]
#
# Options:
#   -o, --owner <n>       GitHub owner/organization (required)
#   -r, --repo <n>        Repository name (required)
#   -s, --store <path>    Token cache file (default: .github_pat_store)
#   -t, --tfvars <path>   Terraform vars file (default: github_secrets.tfvars)
#   -h, --help            Show help
#
# Requires: gh CLI (run `gh auth login` first)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { printf "${BLUE} INFO ${NC}    %s\n" "$*"; }
warn()    { printf "${YELLOW} WARNING ${NC} %s\n" "$*" >&2; }
success() { printf "${GREEN} SUCCESS ${NC} %s\n" "$*"; }
error()   { printf "${RED} ERROR ${NC}   %s\n" "$*" >&2; }

# Defaults
OWNER=""
REPO=""
STORE_FILE=".github_pat_store"
TFVARS_FILE="github_secrets.tfvars"
FINAL_TOKEN=""

# Scopes needed: repo covers secrets + variables, user for token introspection
REQUIRED_SCOPES="repo,user"

show_usage() {
  cat <<EOF
Usage: $(basename "$0") -o <owner> -r <repo> [options]

Required:
  -o, --owner <n>       GitHub owner or organization
  -r, --repo <n>        Repository name

Optional:
  -s, --store <path>    Token storage file (default: $STORE_FILE)
  -t, --tfvars <path>   Output tfvars file (default: $TFVARS_FILE)
  -h, --help            Show this help

Examples:
  $(basename "$0") -o myorg -r myapp
  $(basename "$0") -o myorg -r myapp -s secrets/.pat -t terraform/github.tfvars
EOF
  exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--owner)  OWNER="$2"; shift 2 ;;
    -r|--repo)   REPO="$2"; shift 2 ;;
    -s|--store)  STORE_FILE="$2"; shift 2 ;;
    -t|--tfvars) TFVARS_FILE="$2"; shift 2 ;;
    -h|--help)   show_usage ;;
    *) error "Unknown option: $1"; show_usage ;;
  esac
done

# Validate required arguments
if [[ -z "$OWNER" ]] || [[ -z "$REPO" ]]; then
  error "Both --owner and --repo are required"
  exit 1
fi

# Basic input validation
if ! [[ "$OWNER" =~ ^[A-Za-z0-9._-]+$ ]] || ! [[ "$REPO" =~ ^[A-Za-z0-9._-]+$ ]]; then
  error "Invalid owner or repo name"
  exit 1
fi

# Check gh CLI is available
if ! command -v gh &>/dev/null; then
  error "gh CLI is required. Install it from https://cli.github.com"
  exit 1
fi

# Verify the target repo exists and is accessible
verify_repo() {
  info "Verifying ${OWNER}/${REPO}..."
  if ! gh repo view "${OWNER}/${REPO}" &>/dev/null; then
    error "Repository ${OWNER}/${REPO} not found or not accessible"
    exit 1
  fi
  success "Repository ${OWNER}/${REPO} is accessible"
}

# Validate a token: check it's alive AND has the required scopes
validate_token() {
  local token="$1"

  # Check the token is alive
  local http_code
  http_code=$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: token $token" \
    "https://api.github.com/user")

  if [[ "$http_code" != "200" ]]; then
    warn "Stored token is no longer valid (HTTP $http_code)"
    return 1
  fi

  # Check scopes via the X-OAuth-Scopes response header
  local scopes
  scopes=$(curl -s -D - -o /dev/null \
    -H "Authorization: token $token" \
    "https://api.github.com/user" | grep -i "^x-oauth-scopes:" | sed 's/^[^:]*://;s/\r//;s/ //g')

  # We need at least 'repo' in the scopes
  if echo "$scopes" | grep -q "repo"; then
    return 0
  fi

  warn "Stored token is missing required scopes (has: $scopes)"
  return 1
}

# Read and validate a previously cached token
read_stored_token() {
  if [[ ! -f "$STORE_FILE" ]]; then
    return 1
  fi

  # Verify and fix permissions
  local perms
  perms=$(stat -c '%a' "$STORE_FILE" 2>/dev/null || stat -f '%Lp' "$STORE_FILE" 2>/dev/null) || {
    error "Cannot determine permissions on $STORE_FILE"
    exit 1
  }
  if [[ "$perms" != "600" ]]; then
    warn "Fixing insecure permissions on $STORE_FILE ($perms → 600)"
    chmod 600 "$STORE_FILE"
  fi

  local stored
  stored=$(cat "$STORE_FILE" 2>/dev/null || true)
  [[ -z "$stored" ]] && return 1

  if validate_token "$stored"; then
    success "Found valid cached token"
    FINAL_TOKEN="$stored"
    return 0
  fi

  # Token is dead or missing scopes — remove it
  rm -f "$STORE_FILE"
  return 1
}

# Obtain a token — use the existing gh token first, only refresh if it fails
obtain_token() {
  # Try the current gh token first — no browser needed
  local token
  token=$(gh auth token 2>/dev/null) || true

  if [[ -n "$token" ]] && validate_token "$token"; then
    FINAL_TOKEN="$token"
    success "Token obtained from gh CLI"
    return
  fi

  # Current token is missing or invalid — refresh with the required scopes
  warn "Current gh token is invalid or missing scopes. Re-authenticating..."
  if ! gh auth refresh --scopes "$REQUIRED_SCOPES" 2>&1; then
    error "gh auth refresh failed"
    exit 1
  fi

  token=$(gh auth token 2>/dev/null) || {
    error "Failed to retrieve token after refresh"
    exit 1
  }

  if [[ -z "$token" ]] || ! validate_token "$token"; then
    error "Freshly obtained token failed validation"
    exit 1
  fi

  FINAL_TOKEN="$token"
  success "Token obtained successfully"
}

# Persist the token to the store file
persist_token() {
  local dir
  dir=$(dirname "$STORE_FILE")
  [[ "$dir" != "." ]] && mkdir -p "$dir"

  echo -n "$FINAL_TOKEN" > "$STORE_FILE"
  chmod 600 "$STORE_FILE"
  success "Token cached to $STORE_FILE"
}

# Write the tfvars file
write_tfvars() {
  local dir
  dir=$(dirname "$TFVARS_FILE")
  [[ "$dir" != "." ]] && mkdir -p "$dir"

  cat > "$TFVARS_FILE" <<EOF
# Generated by create_github_pat.sh on $(date -u +%Y-%m-%d)
# Repository: ${OWNER}/${REPO}

github_owner                 = "${OWNER}"
github_repo_name             = "${REPO}"
github_personal_access_token = "${FINAL_TOKEN}"
EOF
  chmod 600 "$TFVARS_FILE"
  success "Terraform vars written to $TFVARS_FILE"
}

# Update .gitignore if inside a git repo
update_gitignore() {
  if ! git rev-parse --git-dir &>/dev/null 2>&1; then
    return
  fi
  for file in "$STORE_FILE" "$TFVARS_FILE"; do
    if ! grep -qxF "$file" .gitignore 2>/dev/null; then
      echo "$file" >> .gitignore
    fi
  done
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  info "=== GitHub PAT Manager ==="
  info "Target: ${OWNER}/${REPO}"

  verify_repo

  # Path 1: reuse a cached token if it's still good
  if ! read_stored_token; then
    # Path 2: get a fresh one via gh auth refresh
    obtain_token
    persist_token
  fi

  write_tfvars
  update_gitignore

  info "=== Done ==="
  info "Token store : $STORE_FILE"
  info "Tfvars file : $TFVARS_FILE"
}

main "$@"