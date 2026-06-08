import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

/**
 * 錯誤報告產生腳本 (Frontend 專用版)
 * 建議位置: frontend/scripts/generate-error-reports.js
 */

// 確保路徑相對於執行指令的目錄 (通常是 frontend/)
const OUTPUT_DIR = 'lintAndTypeError_Check';
const LINT_REPORT = path.join(OUTPUT_DIR, 'lint-report.txt');
const TYPECHECK_REPORT = path.join(OUTPUT_DIR, 'typecheck-report.txt');

// 1. 建立輸出資料夾
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const mode = process.argv[2] || 'all';
const strictMode = process.argv.includes('--strict');

function runCommand(command, outputFile, label) {
  console.log(`\n🔍 Running ${label}...`);

  if (fs.existsSync(outputFile)) {
    fs.unlinkSync(outputFile);
  }

  try {
    // 執行命令，捕捉輸出
    const output = execSync(command, {
      encoding: 'utf8',
      stdio: 'pipe',
      cwd: process.cwd() // 確保在 frontend/ 根目錄執行
    });

    fs.writeFileSync(outputFile, output);
    console.log(`✅ ${label} completed - Report saved to: ${outputFile}`);
    return true;
  } catch (error) {
    const output = error.stdout || error.stderr || error.message;
    fs.writeFileSync(outputFile, output);
    
    console.log(`⚠️  ${label} found issues - Report saved to: ${outputFile}`);
    
    // 顯示前 3 行預覽，方便快速查看錯誤類型
    const lines = output.split('\n').filter(line => line.trim()).slice(0, 3);
    if (lines.length > 0) {
      console.log(`   📝 Preview: ${lines[0].substring(0, 80)}`);
    }
    return false;
  }
}

console.log('📊 Starting Frontend Quality Check...');
console.log(`Project Root: ${process.cwd()}\n`);

let success = true;

// 執行 ESLint
if (mode === 'lint' || mode === 'all') {
  // . 代表檢查當前目錄 (frontend/)
  success = runCommand('npx eslint . --no-cache --max-warnings 0', LINT_REPORT, 'ESLint') && success;
}

// 執行 TypeScript Check
if (mode === 'typecheck' || mode === 'all') {
  success = runCommand('npx tsc --noEmit --pretty false', TYPECHECK_REPORT, 'TypeScript Check') && success;
}

console.log('\n' + '='.repeat(50));
if (success) {
  console.log('🎉 ALL CHECKS PASSED!');
} else {
  console.log('❌ ISSUES DETECTED - PLEASE CHECK REPORTS');
}
console.log(`Directory: ${path.resolve(OUTPUT_DIR)}`);
console.log('='.repeat(50) + '\n');

if (strictMode && !success) {
  process.exit(1);
}
process.exit(0);
