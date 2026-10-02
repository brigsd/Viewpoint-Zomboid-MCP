#version 330

in vec2 vUv;
uniform sampler2D uColor;
uniform sampler2D uAlbedo;
uniform sampler2D uGi;
uniform sampler2D uVolume;
uniform sampler2D uBloom;
uniform vec2 uGiSize;
uniform int uDebugView;
uniform float uGiOn;
uniform float uVolumeOn;
uniform float uBloomStrength;
uniform float uExposure;
uniform vec3 uFogColor;
uniform vec2 uFogRange;
uniform vec2 uHaze;
out vec4 fragColor;

#include "lib/camera.glsl"
#include "lib/common.glsl"
#include "lib/fog.glsl"
#include "lib/fog_amount.glsl"

#ifndef OPTION_EXPOSURE
#define OPTION_EXPOSURE 1.0
#endif
#ifndef OPTION_SHARPENING
#define OPTION_SHARPENING 0.4
#endif

void main() {
  vec2 uv = vUv;
  vec3 color;

  // High-performance smart sharpening
#if OPTION_SHARPENING > 0
  vec2 texel = 1.0 / textureSize(uColor, 0);
  vec3 blur = (texture(uColor, uv + vec2(texel.x, 0.0)).rgb +
               texture(uColor, uv - vec2(texel.x, 0.0)).rgb +
               texture(uColor, uv + vec2(0.0, texel.y)).rgb +
               texture(uColor, uv - vec2(0.0, texel.y)).rgb) * 0.25;
  color = clamp(texture(uColor, uv).rgb + (texture(uColor, uv).rgb - blur) * OPTION_SHARPENING, 0.0, 4.0);
#else
  color = texture(uColor, uv).rgb;
#endif

  if (uDebugView != 0) { fragColor = vec4(color, 1.0); return; }

  if (any(isnan(color)) || any(isinf(color))) color = vec3(0.0);
  float depth = texture(uDepth, uv).r;
  vec3 pos = scenePos(uv, depth);

  if (depth < 1.0) {
    float fog = max(fogAt(linearDepth(depth), uFogRange), hazeAt(distance(pos, uEye), uHaze));
    color = mix(color, fogColor(uFogColor, normalize(pos - uEye)), fog);
  }

  color = shoulder(max(color, vec3(0.0)) * (uExposure * OPTION_EXPOSURE));
  color += (ign(gl_FragCoord.xy + 17.0) - 0.5) / 255.0;
  fragColor = vec4(color, 1.0);
}
