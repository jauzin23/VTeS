const fs = require('fs');
const path = require('path');

const outPath = path.join(__dirname, 'out');
const distPath = path.join(__dirname, 'dist');

try {
  if (fs.existsSync(distPath)) {
    console.log('Cleaning up existing dist folder...');
    fs.rmSync(distPath, { recursive: true, force: true });
  }

  if (fs.existsSync(outPath)) {
    console.log('Renaming out folder to dist...');
    fs.renameSync(outPath, distPath);
    console.log('Post-build process completed successfully!');
  } else {
    console.error('Error: "out" folder not found. Next.js export might have failed.');
    process.exit(1);
  }
} catch (err) {
  console.error('Post-build processing failed:', err);
  process.exit(1);
}
