'use strict';
/**
 * lib/constants.js  —  常量集中管理
 */
const path = require('path');

const SKILL_DIR = path.resolve(__dirname, '..'); // .../aistudio-design-plan/scripts

const DEFAULT_SI = path.resolve(SKILL_DIR, '..', 'assets', 'system_instructions.txt');

const DEFAULT_PROFILE =
  'C:/Users/nicho/WorkBuddy/2026-08-01-16-56-12/aistudio-design-plan-profile';

// 浏览器可执行路径：默认系统 Chrome；设 CHROME_EXE 环境变量可覆盖为专用隐身浏览器（如 CloakBrowser 的 stealth Chromium 二进制）
const CHROME_EXE = process.env.CHROME_EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE_URL = 'https://aistudio.google.com/prompts/new_chat';
const DEFAULT_PROXY = 'http://127.0.0.1:7897';

const TARGET_MODEL = 'gemini-3.1-pro-preview';
const BANNED_MODELS = []; // gemini-3.1-pro-preview 走每日免费额度，不需密钥，已解禁

// DOM 选择器（沿用 aistudio-image-bridge 已验证资产）
const SEL_PROMPT = 'textarea[aria-label="Enter a prompt"], textarea[placeholder*="Start typing"]';
const SEL_MODEL_NAME = '[data-test-id="model-name"]';
const SEL_BACKDROP = '.cdk-overlay-backdrop-showing';
const SI_LABEL = 'System instructions';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

module.exports = {
  SKILL_DIR,
  DEFAULT_SI,
  DEFAULT_PROFILE,
  CHROME_EXE,
  BASE_URL,
  DEFAULT_PROXY,
  TARGET_MODEL,
  BANNED_MODELS,
  SEL_PROMPT,
  SEL_MODEL_NAME,
  SEL_BACKDROP,
  SI_LABEL,
  sleep,
};
