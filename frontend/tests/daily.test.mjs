import test from 'node:test';
import assert from 'node:assert/strict';
import { dailyMonthCells, shiftDailyMonth, dailyRate, dailySeconds } from '../src/daily-view.js';
test('daily calendar uses a stable Monday-first grid across leap years and year boundaries',()=>{
 const cells=dailyMonthCells('2026-10');assert.equal(cells.length,35);assert.equal(cells[0].date,'2026-09-28');assert.equal(cells.filter(c=>c.inMonth).length,31);
 assert.equal(dailyMonthCells('2026-03').length,42);
 assert.equal(dailyMonthCells('2024-02').filter(c=>c.inMonth).length,29);
 assert.equal(shiftDailyMonth('2026-12',1),'2027-01');assert.equal(shiftDailyMonth('2026-01',-1),'2025-12');
});
test('daily display preserves unknown metrics and separates wall-time units',()=>{
 assert.equal(dailyRate(null),'—');assert.equal(dailyRate(0),'0.0%');assert.equal(dailyRate(1),'100.0%');
 assert.equal(dailySeconds(null),'—');assert.equal(dailySeconds(120),'2.0min');
});
