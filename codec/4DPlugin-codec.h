/* --------------------------------------------------------------------------------
 #
 #	4DPlugin-codec.h
 #	source generated by 4D Plugin Wizard
 #	Project : codec
 #	author : miyako
 #	2020/02/03
 #  
 # --------------------------------------------------------------------------------*/

#ifndef PLUGIN_CODEC_H
#define PLUGIN_CODEC_H

#include "4DPluginAPI.h"

#include "C_BLOB.h"
#include "C_LONGINT.h"

#include <cppcodec/base32_crockford.hpp>
#include <cppcodec/base32_hex.hpp>
#include <cppcodec/base32_rfc4648.hpp>

#include <cppcodec/base64_rfc4648.hpp>
#include <cppcodec/base64_url.hpp>
#include <cppcodec/base64_url_unpadded.hpp>

#include <cppcodec/hex_upper.hpp>
#include <cppcodec/hex_lower.hpp>

#pragma mark -

void codec_encode(PA_PluginParameters params);
void codec_decode(PA_PluginParameters params);

typedef enum
{
    base64_rfc4648 = 0,
    base64_url,
    base64_url_unpadded,
    base32_rfc4648,
    base32_crockford,
    base32_hex,
    hex_upper,
    hex_lower
    
}codec_t;

#endif /* PLUGIN_CODEC_H */
