/** Portable local data root; never derives an installation path from the cloud workspace. */
import {homedir} from 'node:os';
import {join,resolve} from 'node:path';
export function runtimeRoot(env=process.env,home=homedir()) {
  return resolve(env.TRITON_HARNESS_ROOT || join(env.XDG_DATA_HOME || join(home,'.local','share'),'triton-dev-harness'));
}
