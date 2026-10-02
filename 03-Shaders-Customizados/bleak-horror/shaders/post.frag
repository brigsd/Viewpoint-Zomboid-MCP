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
#define OPTION_EXPOSURE 0.9
#endif
#ifndef OPTION_CONTRAST
#define OPTION_CONTRAST 1.35
#endif
#ifndef OPTION_DESATURATION
#define OPTION_DESATURATION 0.45
#endif
#ifndef OPTION_COLDSHIFT
#define OPTION_COLDSHIFT 0.4
#endif
#ifndef OPTION_VIGNETTE
#define OPTION_VIGNETTE 1
#endif
#ifndef OPTION_VIGNETTESTRENGTH
#define OPTION_VIGNETTESTRENGTH 0.85
#endif
#ifndef OPTION_FILMGRAIN
#define OPTION_FILMGRAIN 1
#endif
#ifndef OPTION_GRAINAMOUNT
#define OPTION_GRAINAMOUNT 0.04
#endif

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
const vec3 COLD_TINT = vec3(0.72, 0.84, 0.95);

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
  vec3 color = texture(uColor, vUv).rgb;
  if (uDebugView == 1 || uDebugView == 2 || uDebugView == 6) { fragColor = vec4(color, 1.0); return; }
  float depth = texture(uDepth, vUv).r;
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
  vec3 pos = scenePos(vUv, depth);
  if (depth < 1.0) {
    color = color * mix(vec3(0.68, 0.70, 0.75), vec3(1.0), gi.a) + texture(uAlbedo, vUv).rgb * gi.rgb;
  }
  color = color * volume.a + volume.rgb;
  if (depth < 1.0) {
    float fog = max(fogAt(linearDepth(depth), uFogRange), hazeAt(distance(pos, uEye), uHaze));
    color = mix(color, fogColor(uFogColor, normalize(pos - uEye)), fog);
  }
  if (uBloomStrength > 0.0) color += texture(uBloom, vUv).rgb * (uBloomStrength * 0.7);

  // Bleak Horror grading
  color = max(color, vec3(0.0)) * (uExposure * OPTION_EXPOSURE);
  float luma = dot(color, LUMA);

  // Desaturation
  color = mix(color, vec3(luma), OPTION_DESATURATION);

  // Cold shift in shadows
  vec3 coldShadow = mix(color * COLD_TINT, color, clamp(luma * 2.0, 0.0, 1.0));
  color = mix(color, coldShadow, OPTION_COLDSHIFT);

  // High contrast curve
  color = pow(color, vec3(OPTION_CONTRAST));

  // Shoulder tone mapping
  color = shoulder(color);

  // Vignette
#if OPTION_VIGNETTE
  vec2 coord = (vUv - 0.5) * vec2(1.2, 1.0);
  float dist = dot(coord, coord);
  float vig = clamp(1.0 - dist * OPTION_VIGNETTESTRENGTH * 1.5, 0.0, 1.0);
  color *= vig * vig;
#endif

  // Film Grain
#if OPTION_FILMGRAIN
  float noise = ign(gl_FragCoord.xy + fract(pos.x + pos.y + pos.z) * 100.0) - 0.5;
  color += noise * OPTION_GRAINAMOUNT;
#endif

  // Dither
  color += (ign(gl_FragCoord.xy + 17.0) - 0.5) / 255.0;
  fragColor = vec4(max(color, vec3(0.0)), 1.0);
}
