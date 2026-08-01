# 4d-plugin-codec
Encode or decode data, using [cppcodec](https://github.com/tplgy/cppcodec).

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
