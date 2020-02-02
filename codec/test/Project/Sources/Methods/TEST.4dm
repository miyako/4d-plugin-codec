//%attributes = {}
$text:="4D SUMMIT 2020"

CONVERT FROM TEXT:C1011($text;"utf-8";$data)

$code:=codec encode ($data;base64_rfc4648)
$data:=codec decode ($code;base64_rfc4648)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)

$code:=codec encode ($data;base64_url)
$data:=codec decode ($code;base64_url)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)

$code:=codec encode ($data;base64_url_unpadded)
$data:=codec decode ($code;base64_url_unpadded)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)

$code:=codec encode ($data;base32_rfc4648)
$data:=codec decode ($code;base32_rfc4648)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)

$code:=codec encode ($data;base32_crockford)
$data:=codec decode ($code;base32_crockford)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)

$code:=codec encode ($data;base32_hex)
$data:=codec decode ($code;base32_hex)

ASSERT:C1129(Convert to text:C1012($data;"utf-8")=$text)
