import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
async function scan(dir) {
  for (const entry of await readdir(dir, {withFileTypes:true})) {
    const file = path.join(dir, entry.name)
    if (entry.isDirectory()) await scan(file)
    else if (/\.(tsx?|jsx?)$/.test(file)) {
      const source = await readFile(file, 'utf8')
      if (/dangerouslySetInnerHTML|\.innerHTML\s*=|\[\s*['"]innerHTML['"]\s*\]\s*=/.test(source)) throw new Error(`Unsafe HTML rendering: ${file}`)
    }
  }
}
await scan('src')
console.log('Text-only rendering check passed.')
