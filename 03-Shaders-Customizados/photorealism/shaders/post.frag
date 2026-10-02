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
#ifndef OPTION_CONTRAST
#define OPTION_CONTRAST 1.12
#endif
#ifndef OPTION_SATURATION
#define OPTION_SATURATION 1.06
#endif
#ifndef OPTION_VIBRANCE
#define OPTION_VIBRANCE 0.2
#endif
#ifndef OPTION_SHARPENING
#define OPTION_SHARPENING 0.3
#endif
#ifndef OPTION_BLOOMHAZE
#define OPTION_BLOOMHAZE 0.4
#endif
#ifndef OPTION_CHROMATICABERRATION
#define OPTION_CHROMATICABERRATION 0.001
#endif

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

// ACES Filmic Tone Mapping Curve
vec3 acesFilm(vec3 x) {
  float a = 2.51;
  float b = 0.03;
  float c = 2.43;
  float d = 0.59;
  float e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void upsample(float depth, out vec4 gi, out vec4 volume) {
  float d0 = linearDepth(depth);
  vec2 texel = 1.0 / uGiSize;
  vec2 base = (floor(vUv * uGiSize - 0.5) + 0.5) * texel;
  gi = vec4(0.0); volume = vec4(0.0);
  float weight = 0.0;
  for (int y = 0; y < 2; y++) {
    for (int x = 0; x < 2; x++) {
      vec2 uv = base + vec2(x, y) * texel;
      float d = linearDepth(texture(uDepth, uv).r);
      float w = 1.0 / (1.0 + abs(d - d0) * 8.0 / max(d0, 0.5));
      gi += texture(uGi, uv) * w;
      volume += texture(uVolume, uv) * w;
      weight += w;
    }
  }
  gi /= max(weight, 0.0001);
  volume /= max(weight, 0.0001);
}

void main() {
  vec2 uv = vUv;
  vec3 color;

  // Subtle Chromatic Aberration near edges
#if OPTION_CHROMATICABERRATION > 0
  vec2 toCenter = uv - 0.5;
  float distSq = dot(toCenter, toCenter);
  vec2 caOffset = toCenter * (distSq * OPTION_CHROMATICABERRATION * 10.0);
  color.r = texture(uColor, uv - caOffset).r;
  color.g = texture(uColor, uv).g;
  color.b = texture(uColor, uv + caOffset).b;
#else
  color = texture(uColor, uv).rgb;
#endif

  // Smart Sharpening (High-pass filter)
#if OPTION_SHARPENING > 0
  vec2 texel = 1.0 / textureSize(uColor, 0);
  vec3 blur = (texture(uColor, uv + vec2(texel.x, 0.0)).rgb +
               texture(uColor, uv - vec2(texel.x, 0.0)).rgb +
               texture(uColor, uv + vec2(0.0, texel.y)).rgb +
               texture(uColor, uv - vec2(0.0, texel.y)).rgb) * 0.25;
  color = clamp(color + (color - blur) * OPTION_SHARPENING, 0.0, 4.0);
#endif

  if (uDebugView == 1 || uDebugView == 2 || uDebugView == 6) { fragColor = vec4(color, 1.0); return; }
  float depth = texture(uDepth, uv).r;
  vec4 gi = vec4(0.0, 0.0, 0.0, 1.0), volume = vec4(0.0, 0.0, 0.0, 1.0);
#if PIPELINE_INDIRECT || PIPELINE_VOLUMETRICS
  upsample(depth, gi, volume);
#endif
  if (uDebugView == 3) { fragColor = vec4(volume.rgb * 4.0, 1.0); return; }
  if (uDebugView == 4) { fragColor = vec4(gi.rgb * 4.0, 1.0); return; }

  if (any(isnan(color)) || any(isinf(color))) color = vec3(0.0);
  if (any(isnan(gi)) || any(isinf(gi))) gi = vec4(0.0, 0.0, 0.0, 1.0);
  if (any(isnan(volume)) || any(isinf(volume))) volume = vec4(0.0, 0.0, 0.0, 1.0);
  gi = mix(vec4(0.0, 0.0, 0.0, 1.0), gi, uGiOn);
  volume = mix(vec4(0.0, 0.0, 0.0, 1.0), volume, uVolumeOn);
  vec3 pos = scenePos(uv, depth);
  if (depth < 1.0) {
    color = color * mix(vec3(0.74, 0.75, 0.78), vec3(1.0), gi.a) + texture(uAlbedo, uv).rgb * gi.rgb;
  }
  color = color * volume.a + volume.rgb;
  if (depth < 1.0) {
    float fog = max(fogAt(linearDepth(depth), uFogRange), hazeAt(distance(pos, uEye), uHaze));
    color = mix(color, fogColor(uFogColor, normalize(pos - uEye)), fog);
  }
  if (uBloomStrength > 0.0) {
    color = mix(color, texture(uBloom, uv).rgb / 5.0, uBloomStrength * OPTION_BLOOMHAZE);
  }

  // Exposure & ACES tone mapping
  color = max(color, vec3(0.0)) * (uExposure * OPTION_EXPOSURE);
  color = acesFilm(color);

  // Contrast
  float luma = dot(color, LUMA);
  color = mix(vec3(0.5), color, OPTION_CONTRAST);
  color = clamp(color, 0.0, 1.0);

  // Saturation & Vibrance
  luma = dot(color, LUMA);
  color = mix(vec3(luma), color, OPTION_SATURATION);
  float top = max(color.r, max(color.g, color.b));
  float chroma = top > 1.0e-4 ? (top - min(color.r, min(color.g, color.b))) / top : 0.0;
  color = mix(vec3(luma), color, 1.0 + OPTION_VIBRANCE * (1.0 - chroma));

  // Subtle Natural Vignette
  vec2 coord = (uv - 0.5) * vec2(1.1, 1.0);
  float dist = dot(coord, coord);
  color *= clamp(1.0 - dist * 0.35, 0.0, 1.0);

  // Dither
  color += (ign(gl_FragCoord.xy + 17.0) - 0.5) / 255.0;
  fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}
