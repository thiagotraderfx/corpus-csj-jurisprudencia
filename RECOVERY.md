# Recuperación y learnings (Termux/Android)

## 1. DNS roto en binarios Go (gh, go, hugo)

Síntoma: curl a api.github.com → 200, pero gh falla con "no such host".
Causa: Go busca /etc/resolv.conf; Android no lo provee. Cae en [::1]:53.

Fix permanente:

    mkdir -p "$PREFIX/etc"
    printf 'nameserver 8.8.8.8\nnameserver 1.1.1.1\n' > "$PREFIX/etc/resolv.conf"

Afecta solo a binarios Go; curl sigue con el resolver de Android.

## 2. /tmp no escribible

Síntoma: tee /tmp/x → Permission denied.
Fix: usar `mktemp` (respeta $TMPDIR) o $PREFIX/tmp. Nunca /tmp/x hardcodeado.

## 3. git add falla silencioso con paths inexistentes

Síntoma: git add a.py b.py c.py con b.py inexistente → exit 128, nada
staged, mensaje oculto por 2>/dev/null.
Fix: verificar `[ -e "$f" ]` antes de añadir.

## 4. gh release create no atómico

Síntoma: subir 4 assets falla a mitad → draft huérfano con assets
parciales (tag untagged-<hash>). gh release delete v1.1.0 no lo borra.

Fix robusto:

    gh release create v1.1.0 --draft --notes-file notes.md
    for f in dist/*.tar.gz dist/SHA256SUMS; do
        gh release upload v1.1.0 "$f" --clobber
    done
    gh release edit v1.1.0 --draft=false --latest

Borrar huérfano por API:

    gh api repos/$REPO/releases --jq '.[]|select(.draft)|.id'
    gh api repos/$REPO/releases/$ID -X DELETE

## 5. Paste de heredocs largos en Termux

Pegar un bloque a la vez. Si queda `>` prompt, Ctrl+C (NO Ctrl+D).
Verificar `git status` antes de reintentar. Usar 4 espacios de
indentación en lugar de ``` ``` ``` para que nada se manglera.
