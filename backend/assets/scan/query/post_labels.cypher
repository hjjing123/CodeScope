// Auto-generated. Apply AFTER neo4j-admin import.
// Materialize derived SEG tags stored in n.segLabels into real Neo4j labels.

CREATE INDEX call_selector IF NOT EXISTS FOR (c:Call) ON (c.selector);
CREATE INDEX call_selectors IF NOT EXISTS FOR (c:Call) ON (c.selectors);
CREATE INDEX call_receiverType IF NOT EXISTS FOR (c:Call) ON (c.receiverType);
CREATE INDEX call_receiverTypes IF NOT EXISTS FOR (c:Call) ON (c.receiverTypes);
CREATE INDEX call_methodFullName IF NOT EXISTS FOR (c:Call) ON (c.methodFullName);
CREATE INDEX call_name IF NOT EXISTS FOR (c:Call) ON (c.name);
CREATE INDEX call_argPosition IF NOT EXISTS FOR (c:Call) ON (c.argPosition);
CREATE INDEX call_addLeft IF NOT EXISTS FOR (c:Call) ON (c.addLeft);
CREATE INDEX call_allocationClassName IF NOT EXISTS FOR (c:Call) ON (c.AllocationClassName);
CREATE INDEX call_type IF NOT EXISTS FOR (c:Call) ON (c.type);
CREATE INDEX call_receivers IF NOT EXISTS FOR (c:Call) ON (c.receivers);
CREATE INDEX var_type IF NOT EXISTS FOR (v:Var) ON (v.type);
CREATE INDEX var_name IF NOT EXISTS FOR (v:Var) ON (v.name);
DROP INDEX var_assignRight IF EXISTS;
CREATE TEXT INDEX var_assignRight IF NOT EXISTS FOR (v:Var) ON (v.assignRight);
CREATE INDEX method_name IF NOT EXISTS FOR (m:Method) ON (m.name);
CREATE INDEX method_fullName IF NOT EXISTS FOR (m:Method) ON (m.fullName);
CREATE INDEX stringliteral_name IF NOT EXISTS FOR (l:StringLiteral) ON (l.name);
CREATE INDEX stringliteral_nameLower IF NOT EXISTS FOR (l:StringLiteral) ON (l.nameLower);
CREATE INDEX stringliteral_allocationClassName IF NOT EXISTS FOR (l:StringLiteral) ON (l.AllocationClassName);
CREATE INDEX pom_groupId IF NOT EXISTS FOR (p:PomDependency) ON (p.groupId);
CREATE INDEX pom_artifactId IF NOT EXISTS FOR (p:PomDependency) ON (p.artifactId);
CREATE INDEX pom_realVersion IF NOT EXISTS FOR (p:PomDependency) ON (p.realVersion);
CREATE INDEX pom_file IF NOT EXISTS FOR (p:PomDependency) ON (p.file);
CREATE INDEX gradle_groupId IF NOT EXISTS FOR (g:GradleDependency) ON (g.groupId);
CREATE INDEX gradle_artifactId IF NOT EXISTS FOR (g:GradleDependency) ON (g.artifactId);
CREATE INDEX gradle_realVersion IF NOT EXISTS FOR (g:GradleDependency) ON (g.realVersion);
CREATE INDEX callarg_selectors IF NOT EXISTS FOR (a:CallArg) ON (a.selectors);
DROP INDEX callarg_assignRight IF EXISTS;
CREATE TEXT INDEX callarg_assignRight IF NOT EXISTS FOR (a:CallArg) ON (a.assignRight);
CREATE INDEX methodbinding_paramAnnotations IF NOT EXISTS FOR (m:MethodBinding) ON (m.paramAnnotations);
CREATE INDEX ymlkv_name IF NOT EXISTS FOR (n:YmlKeyValue) ON (n.name);
CREATE INDEX ymlkv_nameLower IF NOT EXISTS FOR (n:YmlKeyValue) ON (n.nameLower);
CREATE INDEX ymlkv_value IF NOT EXISTS FOR (n:YmlKeyValue) ON (n.value);
CREATE INDEX ymlkv_valueLower IF NOT EXISTS FOR (n:YmlKeyValue) ON (n.valueLower);
CREATE INDEX ymlkv_fileName IF NOT EXISTS FOR (n:YmlKeyValue) ON (n.fileName);
CREATE INDEX propskv_name IF NOT EXISTS FOR (n:PropertiesKeyValue) ON (n.name);
CREATE INDEX propskv_nameLower IF NOT EXISTS FOR (n:PropertiesKeyValue) ON (n.nameLower);
CREATE INDEX propskv_value IF NOT EXISTS FOR (n:PropertiesKeyValue) ON (n.value);
CREATE INDEX propskv_valueLower IF NOT EXISTS FOR (n:PropertiesKeyValue) ON (n.valueLower);
CREATE INDEX propskv_fileName IF NOT EXISTS FOR (n:PropertiesKeyValue) ON (n.fileName);
CREATE INDEX xml_qNameLower IF NOT EXISTS FOR (n:XmlElement) ON (n.qNameLower);
CREATE INDEX xml_nameLower IF NOT EXISTS FOR (n:XmlElement) ON (n.nameLower);
CREATE INDEX xml_valueLower IF NOT EXISTS FOR (n:XmlElement) ON (n.valueLower);

CALL () {
  MATCH ()-[r:CALLS]->()
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName <> ''
  MATCH (m:Method {fullName: c.methodFullName})
  MERGE (c)-[:CALLS]->(m)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[r:ARG]->(a:StringLiteral)
  WHERE r.argIndex IS NOT NULL
  SET a.argPosition = coalesce(a.argPosition, r.argIndex),
      a.selectors = CASE WHEN c.selectors IS NOT NULL THEN coalesce(a.selectors, []) + c.selectors ELSE a.selectors END,
      a.selector = CASE WHEN a.selector IS NULL OR a.selector = '' THEN c.selector ELSE a.selector END,
      a.receivers = CASE WHEN c.receivers IS NOT NULL THEN coalesce(a.receivers, []) + c.receivers WHEN c.receiverTypes IS NOT NULL THEN coalesce(a.receivers, []) + c.receiverTypes ELSE a.receivers END,
      a.AllocationClassName = CASE WHEN a.AllocationClassName IS NULL OR a.AllocationClassName = '' THEN coalesce(c.AllocationClassName, a.AllocationClassName) ELSE a.AllocationClassName END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[r:ARG]->(a)
  WHERE r.argIndex IS NOT NULL AND NOT a:Call
  SET a.argPosition = coalesce(a.argPosition, r.argIndex),
      a.selectors = CASE
        WHEN c.selectors IS NULL THEN a.selectors
        WHEN a.selectors IS NULL THEN c.selectors
        ELSE a.selectors + c.selectors
      END,
      a.selector = CASE WHEN a.selector IS NULL OR a.selector = '' THEN c.selector ELSE a.selector END,
      a.receivers = CASE WHEN c.receivers IS NOT NULL THEN coalesce(a.receivers, []) + c.receivers WHEN c.receiverTypes IS NOT NULL THEN coalesce(a.receivers, []) + c.receiverTypes ELSE a.receivers END,
      a.AllocationClassName = CASE WHEN a.AllocationClassName IS NULL OR a.AllocationClassName = '' THEN coalesce(c.AllocationClassName, a.AllocationClassName) ELSE a.AllocationClassName END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[r:ARG]->(a:StringLiteral)
  WHERE r.argIndex = 1 AND a.code IS NOT NULL AND a.code <> ''
  SET c.addLeft = coalesce(c.addLeft, a.code)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)-[:ARG]->(:Method)
  SET n:`Argument`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName STARTS WITH 'java.lang.Runtime.exec' OR
    c.methodFullName STARTS WITH 'java.lang.ProcessBuilder.<init>' OR
    c.methodFullName STARTS WITH 'java.lang.ProcessBuilder.start'
  )
  SET c:`SinkCmd`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ProcessBuilder') OR
        (c.receiverType IS NOT NULL AND c.receiverType CONTAINS 'ProcessBuilder') OR
        (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t CONTAINS 'ProcessBuilder'))
  SET c:`ProcessBuilder`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName STARTS WITH 'java.sql.Statement.execute' OR
    c.methodFullName STARTS WITH 'java.sql.Statement.executeQuery' OR
    c.methodFullName STARTS WITH 'java.sql.Statement.executeUpdate' OR
    c.methodFullName STARTS WITH 'java.sql.PreparedStatement.execute' OR
    c.methodFullName STARTS WITH 'org.springframework.jdbc.core.JdbcTemplate.query' OR
    c.methodFullName STARTS WITH 'org.springframework.jdbc.core.JdbcTemplate.update'
  )
  SET c:`SinkSql`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n)-[:ARG]->(:Call)
  SET n:`CallArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE (v)-[:REF]-()
  SET v:`Reference`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE v:Argument
  SET v:`Reference`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE v.declKind = 'Field'
  SET v:`FieldDeclaration`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.receiverType IS NOT NULL AND c.receiverType <> '') OR
        (c.receiverTypes IS NOT NULL AND size(c.receiverTypes) > 0) OR
        (c.receivers IS NOT NULL AND size(c.receivers) > 0)
  SET c:`Receiver`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)-[:ARG]->(:Method)
  WHERE n.type IN ['HttpServletRequest','ServletRequest']
  SET n:`WebServletArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)-[:ARG]->(m:Method)
  WHERE n.type IN ['HttpServletRequest','ServletRequest'] AND m.name IN ['service','doGet','doPost','doPut','doDelete','doHead','doOptions','doTrace']
  SET n:`WebXmlServletArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)-[:ARG]->(m:Method)
  WHERE n.type IN ['HttpServletRequest','ServletRequest'] AND m.name = 'doFilter'
  SET n:`WebXmlFilterArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n)
  WHERE n.name = 'this' AND any(l IN labels(n) WHERE l IN [
    'SpringControllerArg','JaxrsArg','JaxwsArg','JsfXhtmlArg','StrutsActionArg','ThriftHandlerArg',
    'NettyHandlerArg','JfinalControllerArg','JbootControllerArg','SolonControllerArg','SpringInterceptorArg',
    'JspServiceArg','WebServletArg','WebXmlServletArg','WebXmlFilterArg','HttpHandlerArg','DubboServiceArg','MethodBinding'
  ])
  REMOVE n:SpringControllerArg:JaxrsArg:JaxwsArg:JsfXhtmlArg:StrutsActionArg:ThriftHandlerArg:
         NettyHandlerArg:JfinalControllerArg:JbootControllerArg:SolonControllerArg:SpringInterceptorArg:
         JspServiceArg:WebServletArg:WebXmlServletArg:WebXmlFilterArg:HttpHandlerArg:DubboServiceArg:MethodBinding
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.method = 'preHandle' AND n.type IN ['HttpServletRequest','ServletRequest']
  SET n:`SpringInterceptorArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.method = '_jspService'
  SET n:`JspServiceArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.method = 'handle' AND n.type = 'HttpExchange'
  SET n:`HttpHandlerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:HttpHandlerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:HttpHandlerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.paramAnnotations IS NOT NULL AND size(n.paramAnnotations) > 0 AND any(x IN n.paramAnnotations WHERE
    x CONTAINS 'PathParam' OR
    x CONTAINS 'QueryParam' OR
    x CONTAINS 'HeaderParam' OR
    x CONTAINS 'CookieParam' OR
    x CONTAINS 'MatrixParam' OR
    x CONTAINS 'FormParam' OR
    x CONTAINS 'BeanParam'
  )
  SET n:`JaxrsArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'webservice' OR toLower(x) CONTAINS 'webmethod')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'webservice' OR toLower(x) CONTAINS 'webmethod')) OR
        (n.paramAnnotations IS NOT NULL AND any(x IN n.paramAnnotations WHERE toLower(x) CONTAINS 'webparam'))
  SET n:`JaxwsArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'dubbo')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'dubbo'))
  SET n:`DubboServiceArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'struts' OR toLower(x) CONTAINS 'actionsupport')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'struts' OR toLower(x) CONTAINS 'action')) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/struts')
  SET n:`StrutsActionArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'thrift')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'thrift')) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/thrift')
  SET n:`ThriftHandlerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.method IS NOT NULL AND n.method IN ['channelRead','channelRead0','messageReceived','channelActive','channelInactive']) AND
        (n.type IS NOT NULL AND n.type IN ['ChannelHandlerContext','Channel','ChannelFuture','ChannelPromise']) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/netty')
  SET n:`NettyHandlerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'managedbean' OR toLower(x) CONTAINS 'faces')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'faces' OR toLower(x) CONTAINS 'managedproperty'))
  SET n:`JsfXhtmlArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'actionkey')) OR
        (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'actionkey')) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/jfinal')
  SET n:`JfinalControllerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'jboot')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'jboot')) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/jboot')
  SET n:`JbootControllerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE (n.classAnnotations IS NOT NULL AND any(x IN n.classAnnotations WHERE toLower(x) CONTAINS 'solon')) OR
        (n.methodAnnotations IS NOT NULL AND any(x IN n.methodAnnotations WHERE toLower(x) CONTAINS 'solon')) OR
        (n.file IS NOT NULL AND toLower(n.file) CONTAINS '/solon')
  SET n:`SolonControllerArg`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.paramAnnotations IS NOT NULL AND size(n.paramAnnotations) > 0 AND any(x IN n.paramAnnotations WHERE
    x CONTAINS 'RequestParam' OR
    x CONTAINS 'PathVariable' OR
    x CONTAINS 'RequestBody' OR
    x CONTAINS 'RequestHeader' OR
    x CONTAINS 'CookieValue' OR
    x CONTAINS 'MatrixVariable' OR
    x CONTAINS 'RequestPart' OR
    x CONTAINS 'ModelAttribute' OR
    x CONTAINS 'SessionAttribute' OR
    x CONTAINS 'RequestAttribute' OR
    x CONTAINS 'HttpParam'
  ) AND (n.name IS NULL OR n.name <> 'this')
  SET n:`MethodBinding`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.assignRight IS NOT NULL AND n.assignRight <> '' AND (
    n.assignRight CONTAINS '.getParameter(' OR
    n.assignRight CONTAINS '.getParameterValues(' OR
    n.assignRight CONTAINS '.getParameterMap(' OR
    n.assignRight CONTAINS '.getHeader(' OR
    n.assignRight CONTAINS '.getHeaders(' OR
    (
      (n.assignRight CONTAINS '.getInputStream(' OR n.assignRight CONTAINS '.getReader(') AND
      (
        toLower(n.assignRight) CONTAINS 'request' OR
        toLower(n.assignRight) CONTAINS 'servlet' OR
        toLower(n.assignRight) CONTAINS 'http'
      )
    )
  ) AND (n.name IS NULL OR n.name <> 'this')
  SET n:`MethodBinding`,
      n.paramAnnotations = CASE
        WHEN n.paramAnnotations IS NULL THEN ['HttpParam']
        WHEN any(x IN n.paramAnnotations WHERE x CONTAINS 'HttpParam') THEN n.paramAnnotations
        ELSE n.paramAnnotations + ['HttpParam']
      END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.assignRight IS NOT NULL AND n.assignRight <> ''
  SET n:`AssignLeft`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.declKind = 'Local'
  SET n:`LocalDeclaration`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)
  WHERE m.fullName IS NOT NULL AND m.fullName CONTAINS ':java.lang.String('
  WITH m, m.id + "|return|String" AS rid
  MERGE (r:ReturnArg {id: rid})
  SET r.kind = coalesce(r.kind, 'Var'),
      r.name = coalesce(r.name, 'return'),
      r.type = coalesce(r.type, 'String'),
      r.method = coalesce(r.method, m.name),
      r.file = coalesce(r.file, m.file),
      r.line = coalesce(r.line, m.line),
      r.col = coalesce(r.col, m.col),
      r.code = coalesce(r.code, m.code)
  MERGE (r)-[:ARG]->(m)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Lit)
  WHERE (n.type IS NOT NULL AND (n.type = 'String' OR n.type ENDS WITH '.String' OR n.type CONTAINS 'java.lang.String')) OR (n.code IS NOT NULL AND n.code STARTS WITH '"')
  SET n:`StringLiteral`, n.name = CASE
    WHEN (n.name IS NULL OR n.name = '') AND n.code IS NOT NULL AND n.code STARTS WITH '"' AND n.code ENDS WITH '"' AND size(n.code) >= 2 THEN substring(n.code, 1, size(n.code) - 2)
    ELSE coalesce(n.name, n.code)
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (l:StringLiteral)
  WHERE l.name IS NOT NULL AND l.name <> ''
  SET l.nameLower = toLower(l.name)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (l:StringLiteral)
  WHERE l.name IS NOT NULL AND l.code IS NOT NULL AND l.code STARTS WITH '"' AND l.code ENDS WITH '"' AND NOT l.name STARTS WITH '"' AND NOT l.name STARTS WITH "'"
  WITH l, l.id + '|quoted' AS qid
  MERGE (q:StringLiteral {id: qid})
  SET q.kind = coalesce(q.kind, 'Lit'),
      q.name = coalesce(q.name, '"' + l.name + '"'),
      q.type = coalesce(q.type, l.type),
      q.file = coalesce(q.file, l.file),
      q.line = coalesce(q.line, l.line),
      q.col = coalesce(q.col, l.col),
      q.code = coalesce(q.code, l.code),
      q.argPosition = coalesce(q.argPosition, l.argPosition),
      q.selectors = CASE
        WHEN l.selectors IS NULL THEN q.selectors
        WHEN q.selectors IS NULL THEN l.selectors
        ELSE q.selectors + l.selectors
      END,
      q.selector = CASE WHEN q.selector IS NULL OR q.selector = '' THEN l.selector ELSE q.selector END,
      q.receivers = CASE
        WHEN l.receivers IS NULL THEN q.receivers
        WHEN q.receivers IS NULL THEN l.receivers
        ELSE q.receivers + l.receivers
      END,
      q.AllocationClassName = CASE WHEN q.AllocationClassName IS NULL OR q.AllocationClassName = '' THEN l.AllocationClassName ELSE q.AllocationClassName END
  MERGE (q)-[:REF]->(l)
  MERGE (l)-[:REF]->(q)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE v.assignRight IS NOT NULL AND v.assignRight STARTS WITH '"' AND v.assignRight ENDS WITH '"' AND size(v.assignRight) >= 2 AND v.file IS NOT NULL AND v.file <> '' AND v.line IS NOT NULL AND v.line > 0
  MATCH (l:StringLiteral)
  WHERE (l.code = v.assignRight OR l.name = substring(v.assignRight, 1, size(v.assignRight) - 2)) AND l.file = v.file AND l.line IS NOT NULL AND l.line = v.line
  MERGE (l)-[:REF]->(v)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE v.assignRight IS NOT NULL AND v.assignRight <> '' AND size(v.assignRight) <= 200 AND v.file IS NOT NULL AND v.file <> '' AND v.line IS NOT NULL AND v.line > 0
  WITH v,
    CASE
      WHEN v.assignRight STARTS WITH '"' AND v.assignRight ENDS WITH '"' AND size(v.assignRight) >= 2 THEN substring(v.assignRight, 1, size(v.assignRight) - 2)
      ELSE v.assignRight
    END AS assignVal,
    v.assignRight AS assignRight
  MATCH (l:StringLiteral)
  WHERE l.file = v.file AND l.line IS NOT NULL AND l.line = v.line AND l.name IS NOT NULL AND l.name <> '' AND (
    l.name = assignVal OR
    (l.code IS NOT NULL AND l.code = assignRight)
  )
  MERGE (l)-[:REF]->(v)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Reference)
  WHERE (v.assignRight IS NULL OR v.assignRight = '') AND v.file IS NOT NULL AND v.line IS NOT NULL AND v.line > 0
  MATCH (l:StringLiteral)
  WHERE l.file = v.file AND l.line = v.line AND l.line IS NOT NULL AND l.line > 0
  MERGE (l)-[:REF]->(v)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'eval' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ELProcessor.eval') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'ELProcessor') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ELProcessor','javax.el.ELProcessor'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ELProcessor','javax.el.ELProcessor'])
  ) AND (
    NOT ('createValueExpression' IN c.selectors) OR
    c.receiverTypes IS NULL OR NOT ('ExpressionFactory' IN c.receiverTypes) OR
    c.selector IS NULL OR c.selector = ''
  )
  SET c.selectors = CASE
    WHEN 'createValueExpression' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['createValueExpression']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ExpressionFactory']
    WHEN 'ExpressionFactory' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ExpressionFactory']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'createValueExpression'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'eval' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.mvel2.MVEL') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'MVEL') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MVEL','org.mvel2.MVEL'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MVEL','org.mvel2.MVEL'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['MVEL']
    WHEN 'MVEL' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['MVEL']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'eval'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'eval' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'jdk.jshell.JShell') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['JShell','jdk.jshell.JShell'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['JShell','jdk.jshell.JShell'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['JShell']
    WHEN 'JShell' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['JShell']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'eval'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'execute' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ExpressRunner') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ExpressRunner'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ExpressRunner'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ExpressRunner']
    WHEN 'ExpressRunner' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ExpressRunner']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'execute'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'forName' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.lang.Class') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Class','java.lang.Class'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['Class','java.lang.Class'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Class']
    WHEN 'Class' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Class']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'forName'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'forName' IN c.selectors AND c.receiverTypes IS NOT NULL AND 'Class' IN c.receiverTypes AND
        exists { MATCH (:StringLiteral)-[r:ARG]->(c) WHERE r.argIndex = 1 } AND
        NOT exists { MATCH (:Var)-[r:ARG]->(c) WHERE r.argIndex = 1 }
  SET c.safeReflection = true,
      c.receiverTypes = [x IN c.receiverTypes WHERE NOT x IN ['Class','java.lang.Class']],
      c.receiverType = CASE
        WHEN c.receiverType IN ['Class','java.lang.Class'] THEN ''
        ELSE c.receiverType
      END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'invoke' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.lang.reflect.Method') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Method','java.lang.reflect.Method'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['Method','java.lang.reflect.Method'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Method']
    WHEN 'Method' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Method']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'invoke'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'parseExpression' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'SpelExpressionParser') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['SpelExpressionParser'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['SpelExpressionParser'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['SpelExpressionParser']
    WHEN 'SpelExpressionParser' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['SpelExpressionParser']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'parseExpression'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'parseExpression' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ExpressionParser') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ExpressionParser'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ExpressionParser'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ExpressionParser']
    WHEN 'ExpressionParser' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ExpressionParser']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'parseExpression'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'parseExpression' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'TemplateAwareExpressionParser') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['TemplateAwareExpressionParser'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['TemplateAwareExpressionParser'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['TemplateAwareExpressionParser']
    WHEN 'TemplateAwareExpressionParser' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['TemplateAwareExpressionParser']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'parseExpression'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'process' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.thymeleaf.TemplateEngine.process') OR
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.thymeleaf.ITemplateEngine.process') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['TemplateEngine','ITemplateEngine'])) OR
    (c.receivers IS NOT NULL AND any(t IN c.receivers WHERE t IN ['TemplateEngine','ITemplateEngine']))
  )
  SET c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['TemplateEngine','ITemplateEngine']
    WHEN any(t IN c.receivers WHERE t IN ['TemplateEngine','ITemplateEngine']) THEN c.receivers
    ELSE c.receivers + ['TemplateEngine','ITemplateEngine']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'process'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'processThrottled' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.thymeleaf.TemplateEngine.processThrottled') OR
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.thymeleaf.ITemplateEngine.processThrottled') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['TemplateEngine','ITemplateEngine'])) OR
    (c.receivers IS NOT NULL AND any(t IN c.receivers WHERE t IN ['TemplateEngine','ITemplateEngine']))
  )
  SET c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['TemplateEngine','ITemplateEngine']
    WHEN any(t IN c.receivers WHERE t IN ['TemplateEngine','ITemplateEngine']) THEN c.receivers
    ELSE c.receivers + ['TemplateEngine','ITemplateEngine']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'processThrottled'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['evaluate','mergeTemplate']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.apache.velocity') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Velocity','VelocityEngine','RuntimeServices','RuntimeSingleton'])) OR
    (c.receivers IS NOT NULL AND any(t IN c.receivers WHERE t IN ['Velocity','VelocityEngine','RuntimeServices','RuntimeSingleton']))
  )
  SET c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Velocity','VelocityEngine']
    WHEN any(t IN c.receivers WHERE t IN ['Velocity','VelocityEngine']) THEN c.receivers
    ELSE c.receivers + ['Velocity','VelocityEngine']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['evaluate','mergeTemplate','parse']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'RuntimeServices') OR
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'RuntimeSingleton') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['RuntimeServices','RuntimeSingleton'])) OR
    (c.receivers IS NOT NULL AND any(t IN c.receivers WHERE t IN ['RuntimeServices','RuntimeSingleton']))
  )
  SET c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['RuntimeServices','RuntimeSingleton']
    WHEN any(t IN c.receivers WHERE t IN ['RuntimeServices','RuntimeSingleton']) THEN c.receivers
    ELSE c.receivers + ['RuntimeServices','RuntimeSingleton']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.apache.velocity.Template.merge'
  SET c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'merge'
    ELSE c.selector
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Template']
    WHEN 'Template' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Template']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['template']
    WHEN 'template' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['template']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'com.thoughtworks.xstream.XStream.fromXML'
  SET c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'fromXML'
    ELSE c.selector
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['XStream']
    WHEN 'XStream' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['XStream']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['load','dump']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.yaml.snakeyaml.Yaml') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Yaml','org.yaml.snakeyaml.Yaml'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['Yaml','org.yaml.snakeyaml.Yaml'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Yaml']
    WHEN 'Yaml' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Yaml']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.net.Socket.connect'
  SET c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'connect'
    ELSE c.selector
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Socket']
    WHEN 'Socket' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Socket']
  END,
  c.type = 'Socket'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.net.Socket.getInputStream') OR (
    c.code IS NOT NULL AND c.code CONTAINS '.getInputStream(' AND (
      (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Socket','java.net.Socket'])) OR
      (c.receiverType IS NOT NULL AND c.receiverType IN ['Socket','java.net.Socket'])
    )
  )
  SET c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'getInputStream'
    ELSE c.selector
  END,
  c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['getInputStream']
    WHEN 'getInputStream' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['getInputStream']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Socket']
    WHEN 'Socket' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Socket']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Socket']
    WHEN 'Socket' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['Socket']
  END,
  c.type = 'Socket'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)-[:HAS_CALL]->(c:Call)
  WHERE c.selector = 'getInputStream' AND c.type = 'Socket'
  MERGE (c)-[:IN_METHOD]->(m)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject','uploadPart']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'S3Client') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['S3Client','com.amazonaws.services.s3.AmazonS3Client'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['S3Client','com.amazonaws.services.s3.AmazonS3Client'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['S3Client']
    WHEN 'S3Client' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['S3Client']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'OSSClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['OSSClient','com.aliyun.oss.OSSClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['OSSClient','com.aliyun.oss.OSSClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['OSSClient']
    WHEN 'OSSClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['OSSClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'com.aliyun.oss.OSS') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['OSS','com.aliyun.oss.OSS'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['OSS','com.aliyun.oss.OSS'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['OSS']
    WHEN 'OSS' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['OSS']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['uploadFile']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'COSClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['COSClient','com.qcloud.cos.COSClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['COSClient','com.qcloud.cos.COSClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['COSClient']
    WHEN 'COSClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['COSClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['createFile']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'CfsClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['CfsClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['CfsClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['CfsClient']
    WHEN 'CfsClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['CfsClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['createFile']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'NasClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['NasClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['NasClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['NasClient']
    WHEN 'NasClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['NasClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['put','uploadBytes']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'UploadManager') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['UploadManager','com.qiniu.storage.UploadManager'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['UploadManager','com.qiniu.storage.UploadManager'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['UploadManager']
    WHEN 'UploadManager' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['UploadManager']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['createFrom']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'BlobClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['BlobClient','com.azure.storage.blob.BlobClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['BlobClient','com.azure.storage.blob.BlobClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['BlobClient']
    WHEN 'BlobClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['BlobClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['upload']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'FileClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['FileClient','com.azure.storage.file.share.ShareFileClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['FileClient','com.azure.storage.file.share.ShareFileClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['FileClient']
    WHEN 'FileClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['FileClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['createFrom','create']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'Storage') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Storage','com.google.cloud.storage.Storage'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['Storage','com.google.cloud.storage.Storage'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Storage']
    WHEN 'Storage' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Storage']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['upload']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'StorageClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['StorageClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['StorageClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['StorageClient']
    WHEN 'StorageClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['StorageClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ObsClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ObsClient','com.obs.services.ObsClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ObsClient','com.obs.services.ObsClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ObsClient']
    WHEN 'ObsClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ObsClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['createFile']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'SfsClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['SfsClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['SfsClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['SfsClient']
    WHEN 'SfsClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['SfsClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject','uploadFile']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'BosClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['BosClient','com.baidubce.services.bos.BosClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['BosClient','com.baidubce.services.bos.BosClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['BosClient']
    WHEN 'BosClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['BosClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject','uploadObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'MinioClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MinioClient','io.minio.MinioClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MinioClient','io.minio.MinioClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['MinioClient']
    WHEN 'MinioClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['MinioClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'KsyunClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['KsyunClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['KsyunClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['KsyunClient']
    WHEN 'KsyunClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['KsyunClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['putObject']) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'UcloudClient') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['UcloudClient'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['UcloudClient'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['UcloudClient']
    WHEN 'UcloudClient' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['UcloudClient']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'getValue' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ognl.Ognl') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Ognl','ognl.Ognl'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['Ognl','ognl.Ognl'])
  )
  SET c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Ognl']
    WHEN 'Ognl' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['Ognl']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'getValue'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.io.ObjectInputStream.readObject')
  SET c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'readObject'
    ELSE c.selector
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ObjectInputStream']
    WHEN 'ObjectInputStream' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ObjectInputStream']
  END,
  c.type = 'ObjectInputStream'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'readObject' IN c.selectors AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ObjectInputStream','java.io.ObjectInputStream'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ObjectInputStream','java.io.ObjectInputStream'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ObjectInputStream']
    WHEN 'ObjectInputStream' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ObjectInputStream']
  END,
  c.type = 'ObjectInputStream'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.springframework.jdbc.core.JdbcTemplate')
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['JdbcTemplate']
    WHEN 'JdbcTemplate' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['JdbcTemplate']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'readObject' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'HessianInput.readObject') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'HessianInput') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['HessianInput','com.caucho.hessian.io.HessianInput'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['HessianInput','com.caucho.hessian.io.HessianInput'])
  ) AND (
    NOT ('deserialize' IN c.selectors) OR
    c.receiverTypes IS NULL OR NOT ('HessianSerializer' IN c.receiverTypes) OR
    c.type IS NULL OR c.type <> 'HessianSerializer' OR
    c.selector IS NULL OR c.selector = ''
  )
  SET c.selectors = CASE
    WHEN 'deserialize' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['deserialize']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['HessianSerializer']
    WHEN 'HessianSerializer' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['HessianSerializer']
  END,
  c.type = 'HessianSerializer',
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'deserialize'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'eval' IN c.selectors AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['JShell','jdk.jshell.JShell'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['JShell','jdk.jshell.JShell'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['JShell']
    WHEN 'JShell' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['JShell']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'printStackTrace' IN c.selectors
  SET c.selectors = CASE
    WHEN 'getStackTrace' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['getStackTrace']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(a)
  WHERE c.selectors IS NOT NULL AND 'printStackTrace' IN c.selectors AND (
    (a.type IS NOT NULL AND a.type IN ['PrintWriter','java.io.PrintWriter']) OR
    (a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter') OR
    (a.methodFullName IS NOT NULL AND a.methodFullName CONTAINS 'HttpServletResponse.getWriter')
  )
  SET c.selectors = CASE
    WHEN 'print' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['print']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['PrintWriter']
    WHEN 'PrintWriter' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['PrintWriter']
  END,
  c.receivers = CASE
    WHEN (a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter') OR (a.methodFullName IS NOT NULL AND a.methodFullName CONTAINS 'HttpServletResponse.getWriter') THEN CASE
      WHEN c.receivers IS NULL THEN ['response.getWriter()']
      WHEN 'response.getWriter()' IN c.receivers THEN c.receivers
      ELSE c.receivers + ['response.getWriter()']
    END
    ELSE c.receivers
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (a)-[:ARG]->(c:Call)
  WHERE c.selectors IS NOT NULL AND 'printStackTrace' IN c.selectors AND (
    (a.type IS NOT NULL AND a.type IN ['PrintWriter','java.io.PrintWriter']) OR
    (a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter') OR
    (a.methodFullName IS NOT NULL AND a.methodFullName CONTAINS 'HttpServletResponse.getWriter')
  )
  SET c.selectors = CASE
    WHEN 'print' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['print']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['PrintWriter']
    WHEN 'PrintWriter' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['PrintWriter']
  END,
  c.receivers = CASE
    WHEN (a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter') OR (a.methodFullName IS NOT NULL AND a.methodFullName CONTAINS 'HttpServletResponse.getWriter') THEN CASE
      WHEN c.receivers IS NULL THEN ['response.getWriter()']
      WHEN 'response.getWriter()' IN c.receivers THEN c.receivers
      ELSE c.receivers + ['response.getWriter()']
    END
    ELSE c.receivers
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'getInstance' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'MessageDigest.getInstance') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MessageDigest','java.security.MessageDigest'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MessageDigest','java.security.MessageDigest'])
  ) AND (
    c.type IS NULL OR c.type <> 'MessageDigest' OR
    c.receiverTypes IS NULL OR NOT ('MessageDigest' IN c.receiverTypes)
  )
  SET c.type = 'MessageDigest',
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['MessageDigest']
    WHEN 'MessageDigest' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['MessageDigest']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['update','digest']) AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MessageDigest','java.security.MessageDigest'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MessageDigest','java.security.MessageDigest'])
  ) AND (
    c.type IS NULL OR c.type <> 'MessageDigest'
  )
  SET c.type = 'MessageDigest'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (lit:StringLiteral)-[:ARG]->(gi:Call)
  WHERE (lit.name = 'MD5' OR lit.name = 'SHA-1') AND gi.selectors IS NOT NULL AND 'getInstance' IN gi.selectors AND (
    (gi.methodFullName IS NOT NULL AND gi.methodFullName CONTAINS 'MessageDigest.getInstance') OR
    (gi.receiverTypes IS NOT NULL AND any(t IN gi.receiverTypes WHERE t IN ['MessageDigest','java.security.MessageDigest'])) OR
    (gi.receiverType IS NOT NULL AND gi.receiverType IN ['MessageDigest','java.security.MessageDigest'])
  )
  MATCH (m:Method)-[:HAS_CALL]->(gi)
  MATCH (m)-[:HAS_CALL]->(md:Call)
  WHERE md.selectors IS NOT NULL AND any(x IN md.selectors WHERE x IN ['update','digest']) AND md.type = 'MessageDigest'
  MERGE (lit)-[:ARG]->(md)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:PropertiesKeyValue)
  WHERE n.file IS NOT NULL AND n.file <> ''
  SET n.fileName = split(replace(n.file, '\\', '/'), '/')[size(split(replace(n.file, '\\', '/'), '/')) - 1]
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:PropertiesKeyValue)
  WHERE n.name IS NOT NULL AND n.name <> ''
  SET n.nameLower = toLower(n.name)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:PropertiesKeyValue)
  WHERE n.value IS NOT NULL AND n.value <> ''
  SET n.valueLower = toLower(n.value)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:YmlKeyValue)
  WHERE n.file IS NOT NULL AND n.file <> ''
  SET n.fileName = split(replace(n.file, '\\', '/'), '/')[size(split(replace(n.file, '\\', '/'), '/')) - 1]
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:YmlKeyValue)
  WHERE n.name IS NOT NULL AND n.name <> ''
  SET n.nameLower = toLower(n.name)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:YmlKeyValue)
  WHERE n.value IS NOT NULL AND n.value <> ''
  SET n.valueLower = toLower(n.value)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.isThisReceiver = true
  SET c:`ThisReference`
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:WebServletArg)
  WHERE n.type IN ['HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:WebServletArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:WebXmlServletArg)
  WHERE n.type IN ['HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:WebXmlServletArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:WebXmlFilterArg)
  WHERE n.type IN ['HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:WebXmlFilterArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JaxrsArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JaxrsArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:DubboServiceArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:DubboServiceArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:StrutsActionArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:StrutsActionArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:ThriftHandlerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:ThriftHandlerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:NettyHandlerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:NettyHandlerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JsfXhtmlArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JsfXhtmlArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JaxwsArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JaxwsArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JfinalControllerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JfinalControllerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JbootControllerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JbootControllerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:SolonControllerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:SolonControllerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:JspServiceArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:JspServiceArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.selector IS NULL OR c.selector = '') AND c.selectors IS NOT NULL AND size(c.selectors) > 0
  SET c.selector = c.selectors[0]
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.code IS NOT NULL AND c.code CONTAINS 'getWriter()' AND c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['print','write','append','println','printf','format'])
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['PrintWriter','java.io.PrintWriter']
    WHEN any(t IN c.receiverTypes WHERE t IN ['PrintWriter','java.io.PrintWriter']) THEN c.receiverTypes
    ELSE c.receiverTypes + ['PrintWriter','java.io.PrintWriter']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['response.getWriter()']
    WHEN 'response.getWriter()' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['response.getWriter()']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(g:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['print','write','append','println','printf','format']) AND g.selectors IS NOT NULL AND 'getWriter' IN g.selectors AND (
    (g.methodFullName IS NOT NULL AND g.methodFullName CONTAINS 'HttpServletResponse.getWriter') OR
    (g.receiverTypes IS NOT NULL AND any(t IN g.receiverTypes WHERE t IN ['HttpServletResponse','javax.servlet.http.HttpServletResponse','ServletResponse','javax.servlet.ServletResponse']))
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['PrintWriter','java.io.PrintWriter']
    WHEN any(t IN c.receiverTypes WHERE t IN ['PrintWriter','java.io.PrintWriter']) THEN c.receiverTypes
    ELSE c.receiverTypes + ['PrintWriter','java.io.PrintWriter']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['response.getWriter()']
    WHEN 'response.getWriter()' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['response.getWriter()']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['print','write','append']) AND (
    (c.receiverTypes IS NOT NULL AND 'PrintWriter' IN c.receiverTypes) OR
    (c.receivers IS NOT NULL AND 'response.getWriter()' IN c.receivers)
  )
  SET c.selectors = CASE
    WHEN 'println' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['println']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'println'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.type IS NULL OR c.type = '') AND (c.receiverType IS NOT NULL AND c.receiverType <> '' OR (c.receiverTypes IS NOT NULL AND size(c.receiverTypes) > 0))
  SET c.type = CASE
    WHEN c.receiverTypes IS NOT NULL AND size(c.receiverTypes) > 0 THEN c.receiverTypes[size(c.receiverTypes) - 1]
    WHEN c.receiverType IS NOT NULL AND c.receiverType <> '' THEN c.receiverType
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WITH c, toString(c.receiverType) AS rt
  WHERE c.receiverTypes IS NULL AND rt STARTS WITH '[' AND rt ENDS WITH ']'
  WITH c, [x IN split(replace(replace(rt, '[', ''), ']', ''), ',') | trim(replace(replace(x, '"', ''), "'", ''))] AS rts
  WHERE size(rts) > 1
  SET c.receiverTypes = rts,
      c.receiverType = rts[0]
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (c.receivers IS NULL OR size(c.receivers) = 0) AND c.receiverTypes IS NOT NULL AND size(c.receiverTypes) > 0
  SET c.receivers = c.receiverTypes
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'lookup' IN c.selectors AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['DirContext','InitialDirContext'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['DirContext','InitialDirContext'])
  )
  SET c.selectors = CASE
    WHEN 'search' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['search']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'search'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;


CALL () {
  MATCH (c:Call)-[r:ARG]->(a:Lit)
  WHERE r.argIndex = 0 AND (
    (c.AllocationClassName IS NOT NULL AND c.AllocationClassName = 'Cookie') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['Cookie','javax.servlet.http.Cookie']))
  )
  SET a.AllocationClassName = 'Cookie'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(a:Lit)
  WHERE c.selectors IS NOT NULL AND 'getHeader' IN c.selectors AND a.code IS NOT NULL AND toLower(a.code) IN ['"origin"', "'origin'"]
  SET a.selectors = CASE
    WHEN a.selectors IS NULL THEN ['getHeader']
    WHEN 'getHeader' IN a.selectors THEN a.selectors
    ELSE a.selectors + ['getHeader']
  END,
  a.selector = CASE
    WHEN a.selector IS NULL OR a.selector = '' THEN 'getHeader'
    ELSE a.selector
  END,
  a.name = '"Origin"'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'eval' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'ELProcessor.eval') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'ELProcessor') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['ELProcessor','javax.el.ELProcessor'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['ELProcessor','javax.el.ELProcessor'])
  )
  SET c.selectors = CASE
    WHEN 'createValueExpression' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['createValueExpression']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['ExpressionFactory']
    WHEN 'ExpressionFactory' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['ExpressionFactory']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'createValueExpression'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'readObject' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'HessianInput.readObject') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'HessianInput') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['HessianInput','com.caucho.hessian.io.HessianInput'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['HessianInput','com.caucho.hessian.io.HessianInput'])
  )
  SET c.selectors = CASE
    WHEN 'deserialize' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['deserialize']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['HessianSerializer']
    WHEN 'HessianSerializer' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['HessianSerializer']
  END,
  c.type = 'HessianSerializer',
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'deserialize'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(a)
  WHERE c.selectors IS NOT NULL AND 'printStackTrace' IN c.selectors AND (
    (a.type IS NOT NULL AND a.type IN ['PrintWriter','java.io.PrintWriter']) OR
    (a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter')
  )
  SET c.selectors = CASE
    WHEN 'print' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['print']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['PrintWriter']
    WHEN 'PrintWriter' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['PrintWriter']
  END,
  c.receivers = CASE
    WHEN a.code IS NOT NULL AND a.code CONTAINS 'response.getWriter' THEN CASE
      WHEN c.receivers IS NULL THEN ['response.getWriter()']
      WHEN 'response.getWriter()' IN c.receivers THEN c.receivers
      ELSE c.receivers + ['response.getWriter()']
    END
    ELSE c.receivers
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'getInstance' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'MessageDigest.getInstance') OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MessageDigest','java.security.MessageDigest'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MessageDigest','java.security.MessageDigest'])
  )
  SET c.type = 'MessageDigest',
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['MessageDigest']
    WHEN 'MessageDigest' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['MessageDigest']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['update','digest']) AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t IN ['MessageDigest','java.security.MessageDigest'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['MessageDigest','java.security.MessageDigest'])
  )
  SET c.type = 'MessageDigest'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'prepareStatement' IN c.selectors AND (
    exists {
      MATCH (a:Lit)-[r:ARG]->(c)
      WHERE r.argIndex = 1 AND ((a.code IS NOT NULL AND a.code CONTAINS '?') OR (a.name IS NOT NULL AND a.name CONTAINS '?'))
    } OR
    exists {
      MATCH (c)-[r:ARG]->(a:Lit)
      WHERE r.argIndex = 1 AND ((a.code IS NOT NULL AND a.code CONTAINS '?') OR (a.name IS NOT NULL AND a.name CONTAINS '?'))
    } OR
    exists {
      MATCH (a:Var)-[r:ARG]->(c)
      WHERE r.argIndex = 1 AND (
        (a.assignRight IS NOT NULL AND a.assignRight CONTAINS '?') OR
        exists { MATCH (a)-[:REF]->(v1:Var) WHERE v1.assignRight IS NOT NULL AND v1.assignRight CONTAINS '?' } OR
        exists { MATCH (a)<-[:REF]-(v2:Var) WHERE v2.assignRight IS NOT NULL AND v2.assignRight CONTAINS '?' }
      )
    } OR
    exists {
      MATCH (c)-[r:ARG]->(a:Var)
      WHERE r.argIndex = 1 AND (
        (a.assignRight IS NOT NULL AND a.assignRight CONTAINS '?') OR
        exists { MATCH (a)-[:REF]->(v1:Var) WHERE v1.assignRight IS NOT NULL AND v1.assignRight CONTAINS '?' } OR
        exists { MATCH (a)<-[:REF]-(v2:Var) WHERE v2.assignRight IS NOT NULL AND v2.assignRight CONTAINS '?' }
      )
    }
  )
  SET c.safeSql = true,
      c.receiverTypes = CASE
        WHEN c.receiverTypes IS NULL THEN []
        ELSE [x IN c.receiverTypes WHERE NOT x IN ['Connection','java.sql.Connection']]
      END,
      c.receiverType = CASE
        WHEN c.receiverType IN ['Connection','java.sql.Connection'] THEN ''
        ELSE c.receiverType
      END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'getConnection' IN c.selectors AND (
    (c.methodFullName IS NOT NULL AND (c.methodFullName CONTAINS 'java.sql.DriverManager.getConnection' OR c.methodFullName CONTAINS 'javax.sql.DataSource.getConnection')) OR
    (c.code IS NOT NULL AND c.code CONTAINS 'jdbc:')
  ) AND (
    (c.receiverTypes IS NOT NULL AND any(x IN c.receiverTypes WHERE x IN ['DriverManager','DataSource','java.sql.DriverManager','javax.sql.DataSource'])) OR
    (c.receiverType IS NOT NULL AND c.receiverType IN ['DriverManager','DataSource','java.sql.DriverManager','javax.sql.DataSource'])
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN CASE
      WHEN c.receiverType IS NULL THEN ['java.sql.DriverManager']
      WHEN c.receiverType = 'DataSource' THEN ['javax.sql.DataSource']
      WHEN c.receiverType = 'DriverManager' THEN ['java.sql.DriverManager']
      ELSE [c.receiverType]
    END
    ELSE [x IN c.receiverTypes | CASE x WHEN 'DriverManager' THEN 'java.sql.DriverManager' WHEN 'DataSource' THEN 'javax.sql.DataSource' ELSE x END]
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN c.receiverTypes
    ELSE [x IN c.receivers | CASE x WHEN 'DriverManager' THEN 'java.sql.DriverManager' WHEN 'DataSource' THEN 'javax.sql.DataSource' ELSE x END]
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'parse' IN c.selectors AND (
    (c.receiverTypes IS NOT NULL AND ('JSON' IN c.receiverTypes OR 'com.alibaba.fastjson.JSON' IN c.receiverTypes)) OR
    (c.receivers IS NOT NULL AND ('JSON' IN c.receivers OR 'com.alibaba.fastjson.JSON' IN c.receivers))
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NOT NULL AND 'parseObject' IN c.selectors THEN c.selectors
    ELSE coalesce(c.selectors, []) + ['parseObject']
  END,
  c.selector = CASE
    WHEN c.selector IS NULL OR c.selector = '' THEN 'parseObject'
    ELSE c.selector
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND 'lookup' IN c.selectors AND (
    (c.receiverTypes IS NOT NULL AND 'Context' IN c.receiverTypes) OR
    (c.receivers IS NOT NULL AND 'Context' IN c.receivers)
  ) AND (
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'javax.naming.Context.lookup') OR
    (c.code IS NOT NULL AND c.code CONTAINS 'InitialContext') OR
    (c.receiverType IS NOT NULL AND c.receiverType CONTAINS 'InitialContext')
  )
  SET c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['InitialContext']
    WHEN 'InitialContext' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['InitialContext']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['InitialContext']
    WHEN 'InitialContext' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['InitialContext']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.yaml.snakeyaml.Yaml.load'
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['load']
    WHEN 'load' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['load']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'load' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Yaml']
    WHEN 'Yaml' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Yaml']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Yaml']
    WHEN 'Yaml' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['Yaml']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.yaml.snakeyaml.Yaml.dump'
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['dump']
    WHEN 'dump' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['dump']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'dump' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Yaml']
    WHEN 'Yaml' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Yaml']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Yaml']
    WHEN 'Yaml' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['Yaml']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName CONTAINS 'java.net.Socket.connect' OR
    c.methodFullName CONTAINS 'java.net.SocketImpl.connect'
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['connect']
    WHEN 'connect' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['connect']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'connect' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Socket']
    WHEN 'Socket' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Socket']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['Socket']
    WHEN 'Socket' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['Socket']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName CONTAINS 'SpelExpressionParser.parseExpression' OR
    c.methodFullName CONTAINS 'ExpressionParser.parseExpression' OR
    c.methodFullName CONTAINS 'TemplateAwareExpressionParser.parseExpression'
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['parseExpression']
    WHEN 'parseExpression' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['parseExpression']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'parseExpression' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['SpelExpressionParser','ExpressionParser','TemplateAwareExpressionParser']
    ELSE c.receiverTypes + [x IN ['SpelExpressionParser','ExpressionParser','TemplateAwareExpressionParser'] WHERE NOT x IN c.receiverTypes]
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['SpelExpressionParser','ExpressionParser','TemplateAwareExpressionParser']
    ELSE c.receivers + [x IN ['SpelExpressionParser','ExpressionParser','TemplateAwareExpressionParser'] WHERE NOT x IN c.receivers]
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName CONTAINS 'org.thymeleaf.ITemplateEngine.process' OR
    c.methodFullName CONTAINS 'org.thymeleaf.TemplateEngine.process'
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['process']
    WHEN 'process' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['process']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'process' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['TemplateEngine','ITemplateEngine']
    ELSE c.receiverTypes + [x IN ['TemplateEngine','ITemplateEngine'] WHERE NOT x IN c.receiverTypes]
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['TemplateEngine','ITemplateEngine']
    ELSE c.receivers + [x IN ['TemplateEngine','ITemplateEngine'] WHERE NOT x IN c.receivers]
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName CONTAINS 'org.apache.velocity.app.VelocityEngine.evaluate' OR
    c.methodFullName CONTAINS 'org.apache.velocity.app.VelocityEngine.mergeTemplate' OR
    c.methodFullName CONTAINS 'org.apache.velocity.app.Velocity.evaluate'
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['evaluate']
    WHEN 'evaluate' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['evaluate']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['VelocityEngine','Velocity']
    ELSE c.receiverTypes + [x IN ['VelocityEngine','Velocity'] WHERE NOT x IN c.receiverTypes]
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['VelocityEngine','Velocity']
    ELSE c.receivers + [x IN ['VelocityEngine','Velocity'] WHERE NOT x IN c.receivers]
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND (
    c.methodFullName CONTAINS 'org.apache.velocity.runtime.RuntimeServices.parse' OR
    c.methodFullName CONTAINS 'org.apache.velocity.runtime.RuntimeSingleton.parse'
  )
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['parse']
    WHEN 'parse' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['parse']
  END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['RuntimeServices','RuntimeSingleton']
    ELSE c.receiverTypes + [x IN ['RuntimeServices','RuntimeSingleton'] WHERE NOT x IN c.receiverTypes]
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['RuntimeServices','RuntimeSingleton']
    ELSE c.receivers + [x IN ['RuntimeServices','RuntimeSingleton'] WHERE NOT x IN c.receivers]
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'org.apache.velocity.Template.merge'
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['merge']
    WHEN 'merge' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['merge']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'merge' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['Template']
    WHEN 'Template' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['Template']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['template']
    WHEN 'template' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['template']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'java.beans.XMLDecoder.readObject'
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['readObject']
    WHEN 'readObject' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['readObject']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'readObject' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['XMLDecoder']
    WHEN 'XMLDecoder' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['XMLDecoder']
  END,
  c.type = 'XMLDecoder'
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'com.thoughtworks.xstream.XStream.fromXML'
  SET c.selectors = CASE
    WHEN c.selectors IS NULL THEN ['fromXML']
    WHEN 'fromXML' IN c.selectors THEN c.selectors
    ELSE c.selectors + ['fromXML']
  END,
  c.selector = CASE WHEN c.selector IS NULL OR c.selector = '' THEN 'fromXML' ELSE c.selector END,
  c.receiverTypes = CASE
    WHEN c.receiverTypes IS NULL THEN ['XStream']
    WHEN 'XStream' IN c.receiverTypes THEN c.receiverTypes
    ELSE c.receiverTypes + ['XStream']
  END,
  c.receivers = CASE
    WHEN c.receivers IS NULL THEN ['XStream']
    WHEN 'XStream' IN c.receivers THEN c.receivers
    ELSE c.receivers + ['XStream']
  END
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (
    (c.methodFullName IS NOT NULL AND toLower(c.methodFullName) CONTAINS "mapper.") OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE toLower(t) ENDS WITH 'mapper')) OR
    (c.receiverType IS NOT NULL AND toLower(c.receiverType) ENDS WITH 'mapper')
  )
  AND NOT (
    (c.methodFullName IS NOT NULL AND (
      toLower(c.methodFullName) CONTAINS 'objectmapper' OR
      toLower(c.methodFullName) CONTAINS 'modelmapper' OR
      toLower(c.methodFullName) CONTAINS 'xmlmapper'
    )) OR
    (c.receiverType IS NOT NULL AND (
      toLower(c.receiverType) CONTAINS 'objectmapper' OR
      toLower(c.receiverType) CONTAINS 'modelmapper' OR
      toLower(c.receiverType) CONTAINS 'xmlmapper'
    )) OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE
      toLower(t) CONTAINS 'objectmapper' OR
      toLower(t) CONTAINS 'modelmapper' OR
      toLower(t) CONTAINS 'xmlmapper'
    ))
  )
  AND exists {
    MATCH (c)-[:ARG]->(a:StringLiteral)
    WHERE (a.code IS NOT NULL AND a.code CONTAINS '${') OR (a.name IS NOT NULL AND a.name CONTAINS '${')
  }
  SET c:MybatisAnnotationUnsafeArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE c.selectors IS NOT NULL AND any(x IN c.selectors WHERE x IN ['selectOne','selectList','selectMap','select','insert','update','delete','selectById','selectBatchIds','selectAll']) AND (
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE t CONTAINS 'SqlRunner')) OR
    (c.receiverType IS NOT NULL AND c.receiverType CONTAINS 'SqlRunner') OR
    (c.methodFullName IS NOT NULL AND c.methodFullName CONTAINS 'SqlRunner')
  )
  AND exists {
    MATCH (c)-[:ARG]->(a:StringLiteral)
    WHERE (a.code IS NOT NULL AND a.code CONTAINS '${') OR (a.name IS NOT NULL AND a.name CONTAINS '${')
  }
  SET c:MybatisXmlUnsafeArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)
  WHERE (
    (c.methodFullName IS NOT NULL AND toLower(c.methodFullName) CONTAINS "mapper.") OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE toLower(t) ENDS WITH 'mapper')) OR
    (c.receiverType IS NOT NULL AND toLower(c.receiverType) ENDS WITH 'mapper')
  )
  AND NOT (
    (c.methodFullName IS NOT NULL AND (
      toLower(c.methodFullName) CONTAINS 'objectmapper' OR
      toLower(c.methodFullName) CONTAINS 'modelmapper' OR
      toLower(c.methodFullName) CONTAINS 'xmlmapper'
    )) OR
    (c.receiverType IS NOT NULL AND (
      toLower(c.receiverType) CONTAINS 'objectmapper' OR
      toLower(c.receiverType) CONTAINS 'modelmapper' OR
      toLower(c.receiverType) CONTAINS 'xmlmapper'
    )) OR
    (c.receiverTypes IS NOT NULL AND any(t IN c.receiverTypes WHERE
      toLower(t) CONTAINS 'objectmapper' OR
      toLower(t) CONTAINS 'modelmapper' OR
      toLower(t) CONTAINS 'xmlmapper'
    ))
  )
  SET c:MybatisMethodArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(a:Lit)
  WHERE a.code IS NOT NULL AND toLower(a.code) = 'true'
  SET c:TrueLiteral
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)-[:ARG]->(v:Var)
  WHERE v:Argument
  MERGE (v)-[:ARG]->(m)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)-[r:ARG]->(v:Var)
  WHERE v:Argument
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)-[r:ARG]->(a:ReturnArg)
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (a:ReturnArg)-[:ARG]->(m:Method)
  MERGE (m)-[:ARG]->(a)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[:ARG]->(a)
  MERGE (a)-[:ARG]->(c)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (c:Call)-[r:ARG]->(a)
  WHERE NOT c:CallArg
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (a:StringLiteral)-[:ARG]->(c:Call)
  WHERE c.AllocationClassName IS NOT NULL AND (a.AllocationClassName IS NULL OR a.AllocationClassName = '')
  SET a.AllocationClassName = c.AllocationClassName
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (x:XmlElement)
  WHERE x.innerText IS NULL AND x.value IS NOT NULL
  SET x.innerText = x.value
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (x:XmlElement)
  WHERE (x.name IS NULL OR x.name = '') AND x.qName IS NOT NULL AND x.qName <> ''
  SET x.name = x.qName
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (x:XmlElement)
  WHERE x.qName IS NOT NULL AND x.qName <> ''
  SET x.qNameLower = toLower(x.qName)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (x:XmlElement)
  WHERE x.name IS NOT NULL AND x.name <> ''
  SET x.nameLower = toLower(x.name)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (x:XmlElement)
  WHERE x.value IS NOT NULL AND x.value <> ''
  SET x.valueLower = toLower(x.value)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)
  WHERE (
    (m.classAnnotations IS NOT NULL AND any(x IN m.classAnnotations WHERE
      x IN ['Controller','RestController','RequestMapping','GetMapping','PostMapping','PutMapping','DeleteMapping','PatchMapping'] OR
      toLower(x) ENDS WITH '.controller' OR
      toLower(x) ENDS WITH '.restcontroller' OR
      toLower(x) ENDS WITH '.requestmapping' OR
      toLower(x) ENDS WITH '.getmapping' OR
      toLower(x) ENDS WITH '.postmapping' OR
      toLower(x) ENDS WITH '.putmapping' OR
      toLower(x) ENDS WITH '.deletemapping' OR
      toLower(x) ENDS WITH '.patchmapping'
    )) OR
    (m.methodAnnotations IS NOT NULL AND any(x IN m.methodAnnotations WHERE
      x IN ['Controller','RestController','RequestMapping','GetMapping','PostMapping','PutMapping','DeleteMapping','PatchMapping'] OR
      toLower(x) ENDS WITH '.controller' OR
      toLower(x) ENDS WITH '.restcontroller' OR
      toLower(x) ENDS WITH '.requestmapping' OR
      toLower(x) ENDS WITH '.getmapping' OR
      toLower(x) ENDS WITH '.postmapping' OR
      toLower(x) ENDS WITH '.putmapping' OR
      toLower(x) ENDS WITH '.deletemapping' OR
      toLower(x) ENDS WITH '.patchmapping'
    ))
  )
  SET m:SpringController
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)-[:ARG]->(m:Method)
  WHERE (n.name IS NULL OR n.name <> 'this') AND (
    m:SpringController OR
    (m.classAnnotations IS NOT NULL AND any(x IN m.classAnnotations WHERE
      x IN ['Controller','RestController','RequestMapping','GetMapping','PostMapping','PutMapping','DeleteMapping','PatchMapping'] OR
      toLower(x) ENDS WITH '.controller' OR
      toLower(x) ENDS WITH '.restcontroller' OR
      toLower(x) ENDS WITH '.requestmapping' OR
      toLower(x) ENDS WITH '.getmapping' OR
      toLower(x) ENDS WITH '.postmapping' OR
      toLower(x) ENDS WITH '.putmapping' OR
      toLower(x) ENDS WITH '.deletemapping' OR
      toLower(x) ENDS WITH '.patchmapping'
    )) OR
    (m.methodAnnotations IS NOT NULL AND any(x IN m.methodAnnotations WHERE
      x IN ['Controller','RestController','RequestMapping','GetMapping','PostMapping','PutMapping','DeleteMapping','PatchMapping'] OR
      toLower(x) ENDS WITH '.controller' OR
      toLower(x) ENDS WITH '.restcontroller' OR
      toLower(x) ENDS WITH '.requestmapping' OR
      toLower(x) ENDS WITH '.getmapping' OR
      toLower(x) ENDS WITH '.postmapping' OR
      toLower(x) ENDS WITH '.putmapping' OR
      toLower(x) ENDS WITH '.deletemapping' OR
      toLower(x) ENDS WITH '.patchmapping'
    ))
  )
  SET n:SpringControllerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:SpringControllerArg)
  WHERE n.type IN ['HttpServletRequest','ServletRequest','HttpServletResponse','ServletResponse','HttpSession','Model','ModelMap','RedirectAttributes','BindingResult','Errors','Locale','Principal','Authentication','WebRequest','NativeWebRequest','ModelAndView','SessionStatus']
  REMOVE n:SpringControllerArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (dst:Var)
  WHERE dst.assignRight IS NOT NULL AND dst.assignRight <> '' AND size(dst.assignRight) <= 300
    AND dst.method IS NOT NULL AND dst.method <> ''
    AND dst.file IS NOT NULL AND dst.file <> ''
  MATCH (src:Var)
  WHERE src.id <> dst.id
    AND src.method = dst.method
    AND src.file = dst.file
    AND src.name IS NOT NULL AND src.name <> '' AND size(src.name) >= 2
    AND src.name <> 'this'
    AND (
      dst.assignRight = src.name OR
      dst.assignRight CONTAINS '(' + src.name OR
      dst.assignRight CONTAINS '[' + src.name OR
      dst.assignRight CONTAINS ' ' + src.name OR
      dst.assignRight CONTAINS ',' + src.name OR
      dst.assignRight CONTAINS '=' + src.name OR
      dst.assignRight CONTAINS ':' + src.name OR
      dst.assignRight CONTAINS src.name + ')' OR
      dst.assignRight CONTAINS src.name + ']' OR
      dst.assignRight CONTAINS src.name + '.' OR
      dst.assignRight CONTAINS src.name + ',' OR
      dst.assignRight CONTAINS src.name + ' ' OR
      dst.assignRight CONTAINS src.name + ';'
    )
    AND (
      src.type IS NULL OR dst.type IS NULL OR src.type = dst.type OR
      src.type ENDS WITH dst.type OR dst.type ENDS WITH src.type
    )
  MERGE (src)-[:REF]->(dst)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (m:Method)-[:ARG]->(r:ReturnArg)
  MATCH (c:Call)-[:CALLS]->(m)
  WITH r, collect(DISTINCT c) AS callers
  WHERE size(callers) > 0 AND size(callers) <= 5
  UNWIND callers AS c
  MERGE (r)-[:ARG]->(c)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (v:Var)
  WHERE v.name IS NOT NULL AND v.name <> '' AND v.name <> 'this'
    AND v.assignRight IS NOT NULL AND v.assignRight <> '' AND size(v.assignRight) <= 300
    AND v.method IS NOT NULL AND v.method <> ''
    AND v.file IS NOT NULL AND v.file <> ''
  MATCH (m:Method)
  WHERE m.name = v.method AND m.file = v.file
  MATCH (m)-[:HAS_CALL]->(c:Call)
  WHERE c.selector IS NOT NULL AND c.selector <> '' AND NOT c.selector STARTS WITH '<operator>.'
    AND (
      (c.code IS NOT NULL AND c.code <> '' AND size(c.code) <= 200 AND v.assignRight CONTAINS c.code) OR
      v.assignRight CONTAINS c.selector + '(' OR
      v.assignRight CONTAINS '.' + c.selector + '('
    )
  WITH v, collect(DISTINCT c) AS cands
  WHERE size(cands) > 0 AND size(cands) <= 2
  UNWIND cands AS c
  MERGE (c)-[:REF]->(v)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (n:Var)
  WHERE n.name = 'this' AND any(l IN labels(n) WHERE l IN [
    'SpringControllerArg','JaxrsArg','JaxwsArg','JsfXhtmlArg','StrutsActionArg','ThriftHandlerArg',
    'NettyHandlerArg','JfinalControllerArg','JbootControllerArg','SolonControllerArg','SpringInterceptorArg',
    'JspServiceArg','WebServletArg','WebXmlServletArg','WebXmlFilterArg','HttpHandlerArg','DubboServiceArg',
    'MethodBinding'
  ])
  REMOVE n:SpringControllerArg:JaxrsArg:JaxwsArg:JsfXhtmlArg:StrutsActionArg:ThriftHandlerArg:
         NettyHandlerArg:JfinalControllerArg:JbootControllerArg:SolonControllerArg:SpringInterceptorArg:
         JspServiceArg:WebServletArg:WebXmlServletArg:WebXmlFilterArg:HttpHandlerArg:DubboServiceArg:MethodBinding
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (s:Var)
  WHERE any(l IN labels(s) WHERE l IN [
    'SpringControllerArg','JaxrsArg','JaxwsArg','JsfXhtmlArg','StrutsActionArg','ThriftHandlerArg',
    'NettyHandlerArg','JfinalControllerArg','JbootControllerArg','SolonControllerArg','SpringInterceptorArg',
    'JspServiceArg','WebServletArg','WebXmlServletArg','WebXmlFilterArg','HttpHandlerArg','DubboServiceArg',
    'MethodBinding'
  ])
  SET s:SourceEntryArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (s:Var:SourceEntryArg)
  WHERE s.method IS NOT NULL AND s.method <> '' AND s.file IS NOT NULL AND s.file <> ''
  MATCH (m:Method)
  WHERE m.name = s.method AND m.file = s.file
  MERGE (s)-[:ARG]->(m)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (s:Var:SourceEntryArg)
  WHERE s.name IS NOT NULL AND s.name <> '' AND s.method IS NOT NULL AND s.method <> '' AND s.file IS NOT NULL AND s.file <> ''
  MATCH (a:Var:CallArg)-[:ARG]->(c:Call)
  WHERE a.name = s.name AND a.method = s.method AND a.file = s.file
    AND (s.type IS NULL OR a.type IS NULL OR s.type = a.type)
  MERGE (s)-[:ARG]->(c)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (s:Var:SourceEntryArg)
  WHERE s.name IS NOT NULL AND s.name <> '' AND s.method IS NOT NULL AND s.method <> '' AND s.file IS NOT NULL AND s.file <> ''
  MATCH (v:Var)
  WHERE v.id <> s.id AND v.name = s.name AND v.method = s.method AND v.file = s.file AND (
    v:Reference OR v:CallArg
  )
  AND (s.type IS NULL OR v.type IS NULL OR s.type = v.type)
  MERGE (s)-[:REF]->(v)
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH (s:Var:SourceEntryArg)
  REMOVE s:SourceEntryArg
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH ()-[r:METHOD_ARG]->()
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH ()-[r:AST]->()
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;

CALL () {
  MATCH ()-[r:IN_FILE]->()
  DELETE r
} IN TRANSACTIONS OF 10000 ROWS;
