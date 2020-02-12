# 4d-plugin-codec
Encode or decode data, using [cppcodec](https://github.com/tplgy/cppcodec).

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
||<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" /> |<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" /> |<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />

### Version

<img width="32" height="32" src="https://user-images.githubusercontent.com/1725068/73986501-15964580-4981-11ea-9ac1-73c5cee50aae.png"> <img src="https://user-images.githubusercontent.com/1725068/73987971-db2ea780-4984-11ea-8ada-e25fb9c3cf4e.png" width="32" height="32" />

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
