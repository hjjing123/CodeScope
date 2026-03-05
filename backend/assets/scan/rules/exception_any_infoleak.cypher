MATCH
  (sourceNode)
  WHERE
  (sourceNode.selector = 'getStackTrace')
MATCH
  (sinkNode)
  WHERE
  ('format' IN  sinkNode.selectors AND 'PrintWriter' IN  sinkNode.receiverTypes) OR
  ('write' IN  sinkNode.selectors AND 'PrintWriter' IN  sinkNode.receiverTypes) OR
  ('append' IN  sinkNode.selectors AND 'PrintWriter' IN  sinkNode.receiverTypes) OR
  ('println' IN  sinkNode.selectors AND 'PrintWriter' IN  sinkNode.receiverTypes) OR
  ('print' IN  sinkNode.selectors AND 'PrintWriter' IN  sinkNode.receiverTypes) OR
  ('format' IN  sinkNode.selectors AND 'response.getWriter()' IN  sinkNode.receivers) OR
  ('printf' IN  sinkNode.selectors AND 'response.getWriter()' IN  sinkNode.receivers) OR
  ('print' IN  sinkNode.selectors AND 'ServletOutputStream' IN  sinkNode.receiverTypes) OR
  ('println' IN  sinkNode.selectors AND 'ServletOutputStream' IN  sinkNode.receiverTypes) OR
  ('write' IN  sinkNode.selectors AND 'ServletOutputStream' IN  sinkNode.receiverTypes) OR
  ('sendError' IN  sinkNode.selectors AND 'HttpServletResponse' IN  sinkNode.receiverTypes) OR
  ('addAttribute' IN  sinkNode.selectors AND 'Model' IN  sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[ *..30]->(sinkNode))

RETURN
  p AS path

/*
Chanzi-Separator
异常信息泄露

在Java开发中，将异常信息直接返回给客户端可能会带来多种安全风险，主要包括以下几个方面：

系统内部结构暴露：异常信息可能包含类名、方法名、文件路径、堆栈跟踪等信息，这些内容能够帮助攻击者了解系统的内部实现细节，从而找到系统的弱点。

数据库信息泄露：某些异常（如SQLException）可能会暴露数据库的结构、用户名、密码等敏感信息。

文件系统信息泄露：例如FileNotFoundException可能会暴露服务器的文件系统结构。

Chanzi-Separator
为了避免上述风险，建议采取以下措施：

统一错误处理：创建统一的错误页面或错误响应机制，避免直接向客户端返回详细的异常信息。

日志记录：将详细的异常信息记录到服务器端的日志中，而不是直接返回给客户端。

输入验证：对所有用户输入进行严格的验证，防止恶意输入触发异常。

Chanzi-Separator
*/