// Hand-authored UI fixture. This is never presented as a compilation result.
import { normalizeIRDocument } from './ir-model.js';
const code = `import triton
import triton.language as tl

@triton.jit
def vector_add(X, Y, Z, N: tl.constexpr, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offsets = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offsets < N
    x = tl.load(X + offsets, mask=mask, other=0.0)
    y = tl.load(Y + offsets, mask=mask, other=0.0)
    z = x + y
    tl.store(Z + offsets, z, mask=mask)
`;
const path = '/examples/vector_add.py';
const definitions = [
  ['ttir', 'TTIR', [
    ['module {', null], ['  tt.func public @vector_add(%X: !tt.ptr<f32>, %Y: !tt.ptr<f32>,', 5], ['      %Z: !tt.ptr<f32>) {', 5],
    ['    %pid = tt.get_program_id x : i32', 6], ['    %range = tt.make_range {start = 0, end = 256}', 7],
    ['    %base = arith.muli %pid, %c256 : i32', 7], ['    %offsets = arith.addi %base, %range', 7],
    ['    %mask = arith.cmpi slt, %offsets, %N', 8], ['    %xp = tt.addptr %X, %offsets', 9], ['    %x = tt.load %xp, %mask, %zero', 9],
    ['    %yp = tt.addptr %Y, %offsets', 10], ['    %y = tt.load %yp, %mask, %zero', 10],
    ['    %z = arith.addf %x, %y : tensor<256xf32>', 11], ['    %zp = tt.addptr %Z, %offsets', 12], ['    tt.store %zp, %z, %mask', 12], ['    tt.return', null], ['  }', null], ['}', null],
  ]],
  ['coreir', 'CoreIR', [
    ['module {', null], ['  func.func @vector_add(%X: memref<?xf32>,', 5], ['      %Y: memref<?xf32>, %Z: memref<?xf32>) {', 5],
    ['    %pid = core.program_id 0 : index', 6], ['    %base = arith.muli %pid, %c256 : index', 7],
    ['    scf.for %i = %c0 to %c256 step %c1 {', 7], ['      %idx = arith.addi %base, %i : index', 7],
    ['      %mask = arith.cmpi slt, %idx, %N', 8], ['      scf.if %mask {', 8], ['        %x = memref.load %X[%idx] : memref<?xf32>', 9],
    ['        %y = memref.load %Y[%idx] : memref<?xf32>', 10], ['        %z = arith.addf %x, %y : f32', 11],
    ['        memref.store %z, %Z[%idx] : memref<?xf32>', 12], ['      }', null], ['    }', null], ['    return', null], ['  }', null], ['}', null],
  ]],
  ['txir', 'TxIR', [
    ['module {', null], ['  func.func @vector_add(%X: !tx81.addr,', 5], ['      %Y: !tx81.addr, %Z: !tx81.addr) {', 5],
    ['    %pid = tx81.program_id 0 : i32', 6], ['    %offset = arith.muli %pid, %c1024 : i32', 7],
    ['    %mask = arith.cmpi slt, %offset, %N', 8], ['    %x = tx81.load %X, %offset : vector<256xf32>', 9],
    ['    %y = tx81.load %Y, %offset : vector<256xf32>', 10], ['    %sum = arith.addf %x, %y : vector<256xf32>', 11],
    ['    tx81.store %sum, %Z, %offset', 12], ['    return', null], ['  }', null], ['}', null],
  ]],
  ['llir', 'LLVM IR', [
    ['; Illustrative lowering — not a hardware compilation', null], ['define void @vector_add(ptr %X, ptr %Y, ptr %Z) {', 5],
    ['entry:', null], ['  %pid = call i32 @tx81.program_id(i32 0)', 6], ['  %base = mul i32 %pid, 256', 7],
    ['  %mask = icmp slt i32 %base, 1024', 8], ['  %xp = getelementptr float, ptr %X, i32 %base', 9],
    ['  %x = load <256 x float>, ptr %xp', 9], ['  %yp = getelementptr float, ptr %Y, i32 %base', 10],
    ['  %y = load <256 x float>, ptr %yp', 10], ['  %z = fadd <256 x float> %x, %y', 11],
    ['  %zp = getelementptr float, ptr %Z, i32 %base', 12], ['  store <256 x float> %z, ptr %zp', 12], ['  ret void', null], ['}', null],
  ]],
];
export const IR_DEMO = normalizeIRDocument({ schema_version: 1, kernel: 'vector_add', source_kind: 'illustrative', source_hash: 'illustrative-vector-add-v1',
  source: { code, file_path: path, start_line: 1 }, metadata: { backend: 'tsingmicro · 示意', signature: { X: '*fp32', Y: '*fp32', Z: '*fp32' }, constexprs: { N: 1024, BLOCK: 256 } },
  stages: definitions.map(([id, label, rows]) => ({ id, label, content: rows.map(([text]) => text).join('\n'), mapping: Object.fromEntries(rows.flatMap(([, line], i) => line ? [[i + 1, { file: path, line, column: 0 }]] : [])) })),
});
