# 4d-plugin-codec
encode or decode data, using [cppcodec](https://github.com/tplgy/cppcodec).

```
$text:="4D SUMMIT 2020"

CONVERT FROM TEXT($text;"utf-8";$data)

$code:=codec encode ($data;base64_rfc4648)
$data:=codec decode ($code;base64_rfc4648)

ASSERT(Convert to text($data;"utf-8")=$text)

$code:=codec encode ($data;base64_url)
$data:=codec decode ($code;base64_url)

ASSERT(Convert to text($data;"utf-8")=$text)

$code:=codec encode ($data;base64_url_unpadded)
$data:=codec decode ($code;base64_url_unpadded)

ASSERT(Convert to text($data;"utf-8")=$text)

$code:=codec encode ($data;base32_rfc4648)
$data:=codec decode ($code;base32_rfc4648)

ASSERT(Convert to text($data;"utf-8")=$text)

$code:=codec encode ($data;base32_crockford)
$data:=codec decode ($code;base32_crockford)

ASSERT(Convert to text($data;"utf-8")=$text)

$code:=codec encode ($data;base32_hex)
$data:=codec decode ($code;base32_hex)

ASSERT(Convert to text($data;"utf-8")=$text)
```
