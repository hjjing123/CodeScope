const http = require('http');
const server = http.createServer((req, res) => {
  res.writeHead(200);
  res.end('Hello World\n');
});
server.listen(5173, '127.0.0.1', () => {
  console.log('Server running at http://127.0.0.1:5173/');
});
