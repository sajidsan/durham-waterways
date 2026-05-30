const fs = require('fs');

// Load .env for local dev
if (fs.existsSync('.env')) {
  fs.readFileSync('.env', 'utf8').split('\n')
    .filter(line => line && !line.startsWith('#'))
    .forEach(line => {
      const [key, ...val] = line.split('=');
      if (key) process.env[key.trim()] = val.join('=').trim();
    });
}

const token = process.env.MAPBOX_TOKEN || '';
if (!token) console.warn('Warning: MAPBOX_TOKEN not set — map will not load');

fs.mkdirSync('dist/data', { recursive: true });

const html = fs.readFileSync('index.html', 'utf8').replace('__MAPBOX_TOKEN__', token);
fs.writeFileSync('dist/index.html', html);
fs.copyFileSync('scene.html', 'dist/scene.html');

for (const file of fs.readdirSync('data').filter(f => f.endsWith('.geojson'))) {
  fs.copyFileSync(`data/${file}`, `dist/data/${file}`);
}

console.log('Build complete → dist/');
