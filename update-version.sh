#!/usr/bin/env bash
# Atualiza a versão do MPP Sync, faz commit/push e publica a tag de Release.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

UPDATER_FILE="$ROOT/updater.py"
INSTALLER_FILE="$ROOT/build/installer.iss"

if [[ ! -f "$UPDATER_FILE" || ! -f "$INSTALLER_FILE" ]]; then
  echo "Arquivos de versão não encontrados (updater.py / build/installer.iss)."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Este diretório não é um repositório git."
  exit 1
fi

current_version="$(
  sed -nE 's/^APP_VERSION = "([^"]+)".*/\1/p' "$UPDATER_FILE" | head -n 1
)"

if [[ -z "$current_version" ]]; then
  echo "Não foi possível ler APP_VERSION em updater.py."
  exit 1
fi

IFS='.' read -r major minor patch <<<"$current_version"
major="${major:-0}"
minor="${minor:-0}"
patch="${patch:-0}"

echo "Versão atual: v${current_version}"
echo
echo "Tipo de incremento:"
echo "  0) manter (${current_version})"
echo "  1) patch  (${major}.${minor}.$((patch + 1)))  [padrão]"
echo "  2) minor  (${major}.$((minor + 1)).0)"
echo "  3) major  ($((major + 1)).0.0)"
read -r -p "Escolha [0/1/2/3]: " bump_choice
bump_choice="${bump_choice:-1}"

case "$bump_choice" in
  0)
    new_version="${current_version}"
    ;;
  1|"")
    new_version="${major}.${minor}.$((patch + 1))"
    ;;
  2)
    new_version="${major}.$((minor + 1)).0"
    ;;
  3)
    new_version="$((major + 1)).0.0"
    ;;
  *)
    echo "Opção inválida."
    exit 1
    ;;
esac

tag="v${new_version}"

if git rev-parse "$tag" >/dev/null 2>&1; then
  echo "A tag ${tag} já existe localmente."
  exit 1
fi

echo
read -r -p "Mensagem de commit: " commit_message
if [[ -z "${commit_message// }" ]]; then
  echo "A mensagem de commit é obrigatória."
  exit 1
fi

read -r -p "Notas do Release (opcional, Enter para gerar automático): " release_notes
release_notes="${release_notes:-}"

echo
echo "Resumo:"
echo "  Versão:  ${current_version} -> ${new_version}"
echo "  Tag:     ${tag}"
echo "  Commit:  ${commit_message}"
if [[ -n "$release_notes" ]]; then
  echo "  Notes:   ${release_notes}"
fi
echo
read -r -p "Confirmar commit, push e publicação da tag? [y/N]: " confirm
confirm="$(echo "${confirm:-n}" | tr '[:upper:]' '[:lower:]')"
if [[ "$confirm" != "y" && "$confirm" != "yes" ]]; then
  echo "Cancelado."
  exit 0
fi

# Atualiza arquivos de versão (quando houver incremento)
if [[ "$new_version" != "$current_version" ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' -E "s/^APP_VERSION = \"[^\"]+\"/APP_VERSION = \"${new_version}\"/" "$UPDATER_FILE"
    sed -i '' -E "s/^#define MyAppVersion \"[^\"]+\"/#define MyAppVersion \"${new_version}\"/" "$INSTALLER_FILE"
  else
    sed -i -E "s/^APP_VERSION = \"[^\"]+\"/APP_VERSION = \"${new_version}\"/" "$UPDATER_FILE"
    sed -i -E "s/^#define MyAppVersion \"[^\"]+\"/#define MyAppVersion \"${new_version}\"/" "$INSTALLER_FILE"
  fi
  echo "Versão atualizada nos arquivos."
else
  echo "Mantendo a versão atual nos arquivos."
fi

git add -A

if git diff --cached --quiet; then
  echo "Não há mudanças para commit."
  exit 1
fi

git commit -m "$(cat <<EOF
${commit_message}

EOF
)"

branch="$(git rev-parse --abbrev-ref HEAD)"
remote="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"

if [[ -n "$remote" ]]; then
  git push
else
  echo "Branch local sem upstream. Fazendo push com -u origin ${branch}..."
  git push -u origin "$branch"
fi

git tag -a "$tag" -m "$(cat <<EOF
${release_notes:-Release ${tag}}

EOF
)"

git push origin "$tag"

echo
echo "Concluído."
echo "  Commit enviado em ${branch}"
echo "  Tag publicada: ${tag}"
echo "  O GitHub Actions deve gerar o Release com MPPSync-Setup.exe."
echo "  Acompanhe em: https://github.com/joaoreider/mpp-sync/actions"
