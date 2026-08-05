# Codec source signing identity

The non-scientific provenance tag
`corelm-codec-source-2e8d3b-v1` is an SSH-signed annotated tag that points
directly to codec commit
`2e8d3b1591ee4a1ed822310f330317936871ff2b`, tree
`c0bb15784d252cd5036757bc64765c773a5f16e8`.

The public key is shared with the Core LM cross-model release-signing policy.
Its exact file SHA-256 is
`9d299ff032927caef3f1355fb55c01f206ebf27ef35bcb5da547f962168b1274`
and its OpenSSH fingerprint is
`SHA256:8A4y/GkoFglweSfg3rP21BtWWqIBOeQAUoAJDQM8sMM`. The allowed-signers file
SHA-256 is
`36fb4a170eee7664be32f2a5d562db209fa4f6f1f24667cf6a3ef0166d155c16`.

The private key is not part of this repository and must never be copied into
source, an artifact, a log, or CI. The tag target predates this `signing/`
directory, so durable verification must take the public trust bytes from the
signed cross-model lab tag or the future immutable evidence bundle, not from a
moving codec `main`. Set `CORELM_TRUST_ROOT` to that read-only directory:

```sh
set -eu
git fetch origin tag corelm-codec-source-2e8d3b-v1
: "${CORELM_TRUST_ROOT:?set to the absolute directory containing the public trust files}"
case "$CORELM_TRUST_ROOT" in /*) ;; *) exit 1 ;; esac
sha256_path() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}
test "$(sha256_path "$CORELM_TRUST_ROOT/corelm-crossmodel-v4-signing.pub")" = \
  9d299ff032927caef3f1355fb55c01f206ebf27ef35bcb5da547f962168b1274
test "$(sha256_path "$CORELM_TRUST_ROOT/allowed_signers")" = \
  36fb4a170eee7664be32f2a5d562db209fa4f6f1f24667cf6a3ef0166d155c16
/usr/bin/ssh-keygen -E sha256 \
  -lf "$CORELM_TRUST_ROOT/corelm-crossmodel-v4-signing.pub" \
  | grep -Fq 'SHA256:8A4y/GkoFglweSfg3rP21BtWWqIBOeQAUoAJDQM8sMM'
git -c gpg.format=ssh \
  -c gpg.ssh.program=/usr/bin/ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$CORELM_TRUST_ROOT/allowed_signers" \
  verify-tag corelm-codec-source-2e8d3b-v1
test "$(git rev-parse corelm-codec-source-2e8d3b-v1)" = \
  4c5b2bd2caa985506df17b3ea0da074b5022bd2b
test "$(git rev-list -n 1 corelm-codec-source-2e8d3b-v1)" = \
  2e8d3b1591ee4a1ed822310f330317936871ff2b
test "$(git rev-parse 'corelm-codec-source-2e8d3b-v1^{tree}')" = \
  c0bb15784d252cd5036757bc64765c773a5f16e8
```

This tag authenticates the exact codec source consumed by the published
cross-model development control. It is provenance, not a scientific result
and not a replacement for the signed lab release or its receipt. The complete
two-repository path is the lab's
[`REPRODUCE.md`](https://github.com/ALLPROTO/core-lm-cross-model-lab/blob/main/REPRODUCE.md).
