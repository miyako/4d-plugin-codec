# 4d-plugin-codec
Encode or decode data, using [cppcodec](https://github.com/tplgy/cppcodec).

## Manual source version and Build workflows

Run **Bump version** manually on the selected branch with `patch`, `minor`, or
`major`. It validates source metadata before writing, commits only source version
changes as a single direct child of the selected dispatch SHA, and pushes only
that branch. It creates no tag, release, or Build run. A mandatory executable
pre-push guard requires exactly one update with the originally selected remote
SHA and literal new commit SHA; concurrent advance, rewind, deletion, or even an
identical-result update fails. A moved branch requires a fresh dispatch.

Run **Build** separately using the Actions branch selector. It has **zero inputs**
and every checkout uses the immutable dispatch `github.sha`. Source `X.Y.Z`
determines `vX.Y.Z`, `codec-X.Y.Z.zip`, and `codec-X.Y.Z.dmg`. Windows x64 is
built first with the existing MSBuild v143/Windows SDK 10.0 overrides; macOS keeps
the Default target/configuration, arm64 + x86_64, deployment override 11.0,
existing resources/dependencies, Developer ID signing, both notarizations, and
DMG stapling. There is no branch restriction added to Build. Production build,
signing, notarization, and 4D execution are not part of local regression tests.

Publication has one repository-wide, cross-branch concurrency group with no
running cancellation. Before native work and again after all native gates it
checks the exact remote tag and authenticated, fully paginated release lists,
including drafts. Any existing tag/release, malformed response, authentication,
404, network, or later-page error stops publication. Creation uses separate
POSTs: new tag ref at the selected SHA (then exact remote verification), new
public non-prerelease release, then assets on that newly returned release ID.
The original policy is retained: release name equals tag, empty body, no
generated notes. Nothing is reused, overwritten, clobbered, deleted, retried, or
rolled back automatically.

**Recovery:** inspect the failing run and remote tag, release ID, and uploaded
assets before taking manual action. A tag creation followed by a release failure
retains the tag; an upload failure retains the tag, release, and earlier assets.
Ambiguous responses can also mean creation succeeded remotely. Do not rerun
expecting repair: availability checks intentionally reject this partial state.
A maintainer must decide how to recover it manually or use Bump version and a
fresh Build for a new version.

### Source authority and migration evidence

The default branch was independently verified as `master` through the repository
API and symbolic `refs/remotes/origin/HEAD`. The original `release.yml` ran on
`v*.*.*` tag pushes and manual dispatch with a required `tag` input; original
`bump-version.yml` was manual with the three semantic bump choices. These are the
only workflows, and neither carried an intentional branch restriction.

History followed back to `0105d856007a59d129df88d6823007432a6b2dc7`
(`mv`, workflow introduction; no earlier renamed workflow) and
`fb0a60a952f912c4f7ee556db28e8f3a3b01fda0` explicitly said
“Bumps MARKETING_VERSION”. That was marketing-only authority, not a reason to
coordinate an independent build. The later
`8c2df68ec31ff247a27b6078068e3b6f57ddaf53` header explicitly superseded it:
“MARKETING_VERSION/CURRENT_PROJECT_VERSION AND Info.plist's
CFBundleShortVersionString/CFBundleVersion”. Its commit also promised sync and
added both settings to all six configurations. Its fallback body nevertheless
updated marketing only, leaving current at 1.0.1 after the subsequent source
bumps `3e4ebb6` and `b408730` established marketing/source plist 1.0.3.

The migration repairs those six proven stale current settings to the **existing
1.0.3**, not a new intake version. All three target configurations actually use
`codec copy-Info.plist`, whose short version became `$(MARKETING_VERSION)` in
`fb0a60a`; that reference and its CR-only bytes are preserved. The tracked
`Info.plist` literal is also validated and maintained. Both omit
`CFBundleVersion`, which stays
absent. The copied `English.lproj/InfoPlist.strings` overrides the display with
stale `1.0`; only its two version tokens are repaired to 1.0.3, preserving its
CR-only format, mode, and `Copyright 2020 miyako.`. The helper validates all six
settings, both source plists, references, duplicate keys/assignments, and
localized text before writing; preserves BOM, individual line endings (including
mixed), quoting, whitespace, modes, absent optional keys, and unrelated bytes.
Built plist and localized display are checked too, including binary-plist
localization produced by Xcode. Prebuilt bundles, dependencies, schemas, API
headers, 4D files/counters, and other native project settings are not version
inputs.

Full committed prior-art snapshots were fetched and compared:
`miyako/4d-plugin-arguments@38a45cd0e30dc015ed430e8dd3c95c5c31f4a1fc`
(coordinated six-config helper, publication/guard, binary-plist localization and
native stubs),
`miyako/4d-plugin-process@ec2611e6bbe97e87982cb84bb603462d0458612c`
(coordinated authority),
`miyako/4d-plugin-common-string-algorithm@2606a68201866ec9fcbb38b51462d79215f504ef`,
and `miyako/4d-plugin-window-button@3f14facb9aaaaff0e22eeb8e07531163680c3a8a`
(independent-build counterexamples). The arguments implementation and suites
are adapted to codec's actual two source plists, resource layout, original
toolchains, and copyright rather than transplanting another native project.
Freshness fixes are limited to invalidating rebuilt products (not committed
resources or the downloaded Windows artifact), exact actual Windows output and
artifact paths, separate architecture checks, and requiring both notary results
to be `Accepted`.

Local regression commands (no real native tools):

```sh
actionlint
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/tests -v
```

The `codec` plugin converts binary data to and from text using common encoding schemes — Base64 (standard and URL-safe, padded and unpadded), Base32 (standard, Crockford, and Extended Hex), and hexadecimal (upper- and lower-case). It's a thin 4D wrapper around the [cppcodec](https://github.com/tplgy/cppcodec) C++ library: encoding produces a `Text`, decoding consumes a `Text` and produces a `Blob`.

## Summary

| Command | Returns | Purpose |
|---|---|---|
| [`codec encode`](#codec-encode) | Text | Encode a `Blob` into a text representation using the chosen scheme |
| [`codec decode`](#codec-decode) | Blob | Decode a text representation back into a `Blob` using the chosen scheme |

**Platforms:** Windows and macOS (identical behavior on both — see below).

---

## Requirements & platform notes

- **No platform divergence.** Neither command contains any `#if VERSIONMAC`/`#if VERSIONWIN` branching, and the underlying `cppcodec` library is portable, header-only C++ with no OS API calls. Encoding/decoding results are identical on Windows and macOS.
- **Both parameters are mandatory** on both commands — there is no optional-parameter form. Both parameters are always read unconditionally from the call.
- **Both commands are thread-safe** (declared `threadSafe: true` in the plugin manifest), so they can be called from preemptive processes.
- **Failure is silent, not a 4D error.** An invalid codec constant, or (for `codec decode`) malformed encoded text, does **not** raise a 4D error — it silently returns an empty result (`""` for `codec encode`, an empty `Blob` for `codec decode`). See [Error handling & troubleshooting](#error-handling--troubleshooting) below before relying on either command's output in a validation path.
- **Codec constants.** Both commands take the same set of predefined Longint constants (theme `codec`) as their second parameter:

| Constant | Description |
|---|---|
| `base64_rfc4648` | Standard Base64 (RFC 4648), padded, `+`/`/` alphabet. |
| `base64_url` | URL- and filename-safe Base64 (RFC 4648 §5), padded, `-`/`_` alphabet. |
| `base64_url_unpadded` | Same URL-safe alphabet as `base64_url`, without `=` padding. |
| `base32_rfc4648` | Standard Base32 (RFC 4648), padded, `A`–`Z`/`2`–`7` alphabet. |
| `base32_crockford` | Crockford's Base32 variant — excludes visually ambiguous characters (`I`, `L`, `O`, `U`), unpadded. |
| `base32_hex` | "Extended Hex" Base32 (RFC 4648 §7), padded, `0`–`9`/`A`–`V` alphabet. |
| `hex_upper` | Hexadecimal, uppercase (`A`–`F`). |
| `hex_lower` | Hexadecimal, lowercase (`a`–`f`). |

  You must pass the *same* constant to `codec decode` that was used to `codec encode` the data — decoding with a different scheme than the one used to encode will either fail silently (see below) or, in some cases, succeed but produce garbage bytes.

---

## codec encode

### Syntax

```4d
codec encode ( data ; codec ) : text
```

| Parameter | Type | Description |
|---|---|---|
| `data` | Blob | The binary data to encode. |
| `codec` | Longint | One of the [codec constants](#requirements--platform-notes) selecting the encoding scheme. |
| Result | Text | The encoded text. Empty if `codec` isn't a valid constant, or if encoding fails internally (see [Error handling](#error-handling--troubleshooting)). |

### Description

Encodes the bytes in `data` into a `Text` value using the scheme named by `codec`. An empty input `Blob` encodes to an empty `Text` — that's expected, ordinary behavior, not a failure.

### Example

From the plugin's own test method (`TEST.4dm`):

```4d
$text:="4D SUMMIT 2020"

CONVERT FROM TEXT:C1011($text;"utf-8";$data)

$code:=codec encode ($data;base64_rfc4648)
$data:=codec decode ($code;base64_rfc4648)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)
```

Encoding the same data with a different scheme just by swapping the constant:

```4d
$code:=codec encode ($data;hex_lower)
 // $code now holds a lowercase-hex representation of $data
```

Looping over every available scheme (useful for comparing output sizes/formats):

```4d
ARRAY LONGINT($codecs;8)
$codecs{1}:=base64_rfc4648
$codecs{2}:=base64_url
$codecs{3}:=base64_url_unpadded
$codecs{4}:=base32_rfc4648
$codecs{5}:=base32_crockford
$codecs{6}:=base32_hex
$codecs{7}:=hex_upper
$codecs{8}:=hex_lower

For ($i;1;Size of array($codecs))
	$code:=codec encode ($data;$codecs{$i})
	ALERT(String($codecs{$i})+": "+$code)
End for 
```

---

## codec decode

### Syntax

```4d
codec decode ( code ; codec ) : blob
```

| Parameter | Type | Description |
|---|---|---|
| `code` | Text | The encoded text to decode, in the scheme named by `codec`. |
| `codec` | Longint | One of the [codec constants](#requirements--platform-notes) selecting the decoding scheme. Must match the scheme `code` was actually encoded with. |
| Result | Blob | The decoded binary data. Empty if `codec` isn't a valid constant, or if `code` isn't valid input for the chosen scheme (see [Error handling](#error-handling--troubleshooting)). |

### Description

Decodes `code` back into a `Blob` using the scheme named by `codec`. Pair this with [`codec encode`](#codec-encode) using the same constant to round-trip data, as shown in the test file above.

### Example

From the plugin's own test method (`TEST.4dm`), the full round-trip for one scheme:

```4d
$code:=codec encode ($data;base32_crockford)
$data:=codec decode ($code;base32_crockford)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)
```

Decoding a hex string received from elsewhere (e.g. a web service) back into a `Blob`:

```4d
$data:=codec decode ("48656C6C6F";hex_upper)
 // $data is now the Blob {0x48, 0x65, 0x6C, 0x6C, 0x6F} ("Hello")
```

---

## Error handling & troubleshooting

- **Out-of-range `codec` constant silently returns an empty result.** Both commands range-check `codec` against the valid constant list internally; if it's not one of the documented constants, `codec encode` returns `""` and `codec decode` returns an empty `Blob` — no 4D error is raised. Always pass one of the [documented constants](#requirements--platform-notes), not a raw literal number you've constructed yourself.
- **Malformed input to `codec decode` also fails silently.** If `code` contains characters outside the chosen scheme's alphabet, has invalid padding, or has a length that's invalid for that scheme, the underlying decoder throws internally — this is caught by the plugin and converted into an empty `Blob` result rather than a 4D error or a freeze. If you need to detect this case, you cannot rely on the return value alone (see next point).
- **You can't tell "empty on purpose" from "empty because it failed."** Both an empty-but-valid decode result and a failed decode return the same thing: an empty `Blob`. If your code needs to distinguish a genuinely empty payload from a decode error, validate `code` yourself before calling `codec decode` (e.g. check its length and character set against the scheme you expect), rather than inferring failure from an empty result.
- **Mismatched scheme between encode and decode.** Decoding with a different `codec` constant than the one used to encode will typically hit the malformed-input case above (empty result), but for schemes with compatible alphabets it can succeed while producing incorrect bytes instead of failing at all. Keep the constant used for `codec encode` and the matching `codec decode` call visibly paired in your code (as the test file does).

---

## Quick reference

```4d
 // encode / decode round-trip
CONVERT FROM TEXT:C1011($text;"utf-8";$data)
$code:=codec encode ($data;base64_rfc4648)
$data:=codec decode ($code;base64_rfc4648)

 // available constants (theme "codec")
 // base64_rfc4648, base64_url, base64_url_unpadded,
 // base32_rfc4648, base32_crockford, base32_hex,
 // hex_upper, hex_lower
```
