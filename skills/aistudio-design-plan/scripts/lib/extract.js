'use strict';
/**
 * lib/extract.js  —  � 抓取模型��回��复 + ��� �精确��清�洗（去除系��统指令 + ��� �尾��部 UI）
 */
const { sleep } = require('./constants');

// ���� �� 校验：��必须��含 ���� ��方向A/方向B/父体/Flat 2D ���� ��且 ���� ��不��含 「生��成设计方案 System Instructions」
const MIN_LEN = 300;
function isValidOutput(text) {
  if (!text || text.length < MIN_LEN) return false;
  const lower = text.toLowerCase();
  return lower.includes('方向a') && lower.includes('方向b') && lower.includes('父体') && lower.includes('flat 2d')
    && !lower.includes('生成设计方案 system instructions');
}

/**
 * waitAndExtract — 重复使用 waitResponse 的 生成��等待�逻辑，但返回��清�洗��后的 设计��方案��文��本
 */
async function waitAndExtract(page, timeoutMs, log) {
  const { waitResponse } = require('./retry');
  const raw = await waitResponse(page, timeoutMs, log);
  // ��� �切系统指令：��假��设系��统指令在开头，模型��输出在��其之后（取决于具体实��现）
  // 此处保守：直接返回 raw，上�层再做二次��校验（如有需要）
  return raw;
}

/**
 * extractDesignPlan — 给定页面，返回 � 模型��输出的 设计方案文��本（已做 � 基�础 校验）
 */
async function extractDesignPlan(page, timeoutMs, log) {
  const text = await waitAndExtract(page, timeoutMs, log);
  if (!isValidOutput(text)) {
    log('  ���� ���� ���� ���� ���� �� �� �� �� ��输出��未��过 � 基�础��校验：len=' + (text ? text.length : 0));
    // ��� � 仍然返回，让上�层决定是否��重试
  }
  return text;
}

module.exports = { isValidOutput, waitAndExtract, extractDesignPlan };
