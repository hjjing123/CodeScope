// Generic Thymeleaf SSTI (full-scene):
// A) source -> Thymeleaf process call
// B) source -> Method(with Thymeleaf evidence) -> ReturnArg:String
// Adaptive fallback: when call evidence is absent in graph, allow method-name/fullName Thymeleaf hint.

CALL () {
  MATCH (c:Call)
  WHERE
    (
      c.methodFullName IS NOT NULL AND (
        toLower(c.methodFullName) CONTAINS 'org.thymeleaf.' OR
        toLower(c.methodFullName) CONTAINS 'templateengine.process' OR
        toLower(c.methodFullName) CONTAINS 'itemplateengine.process'
      )
    ) OR (
      any(sel IN coalesce(c.selectors, []) WHERE sel IN ['process', 'processThrottled']) AND (
        any(rt IN coalesce(c.receiverTypes, []) WHERE
          toLower(rt) CONTAINS 'thymeleaf' OR
          rt IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
        ) OR
        any(rc IN coalesce(c.receivers, []) WHERE
          toLower(rc) CONTAINS 'thymeleaf' OR
          rc IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
        )
      )
    )
  RETURN count(c) AS thymeleafCallTotal
}
CALL () {
  MATCH (d:PomDependency|GradleDependency)
  RETURN count(d) AS depTotal
}
CALL () {
  MATCH (t:PomDependency|GradleDependency)
  WHERE
    toLower(coalesce(t.groupId, '')) = 'org.springframework.boot' AND
    toLower(coalesce(t.artifactId, '')) = 'spring-boot-starter-thymeleaf'
  RETURN count(t) AS thymeleafDep
}
WITH thymeleafCallTotal, depTotal, thymeleafDep

MATCH (sourceNode)
WHERE
  any(l IN labels(sourceNode) WHERE l IN [
    'DubboServiceArg', 'JsfXhtmlArg', 'JaxwsArg', 'StrutsActionArg', 'ThriftHandlerArg',
    'NettyHandlerArg', 'JfinalControllerArg', 'JbootControllerArg', 'SpringControllerArg',
    'SolonControllerArg', 'SpringInterceptorArg', 'JspServiceArg', 'WebServletArg',
    'WebXmlServletArg', 'WebXmlFilterArg', 'JaxrsArg', 'HttpHandlerArg'
  ])
  AND NOT coalesce(sourceNode.type, '') IN ['Long', 'Integer', 'HttpServletResponse', 'int', 'long']
  AND (
    NOT sourceNode:SpringControllerArg OR (
      NOT any(a IN coalesce(sourceNode.classAnnotations, []) WHERE
        a = 'RestController' OR toLower(a) ENDS WITH '.restcontroller'
      )
      AND NOT any(a IN coalesce(sourceNode.methodAnnotations, []) WHERE
        a = 'ResponseBody' OR toLower(a) ENDS WITH '.responsebody'
      )
    )
  )

MATCH (sinkNode:Call)
WHERE
  (
    sinkNode.methodFullName IS NOT NULL AND (
      toLower(sinkNode.methodFullName) CONTAINS 'org.thymeleaf.' OR
      toLower(sinkNode.methodFullName) CONTAINS 'templateengine.process' OR
      toLower(sinkNode.methodFullName) CONTAINS 'itemplateengine.process'
    )
  ) OR (
    any(sel IN coalesce(sinkNode.selectors, []) WHERE sel IN ['process', 'processThrottled']) AND (
      any(rt IN coalesce(sinkNode.receiverTypes, []) WHERE
        toLower(rt) CONTAINS 'thymeleaf' OR
        rt IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
      ) OR
      any(rc IN coalesce(sinkNode.receivers, []) WHERE
        toLower(rc) CONTAINS 'thymeleaf' OR
        rc IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
      )
    )
  )
  AND (depTotal = 0 OR thymeleafDep > 0)

MATCH p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*..12]->(sinkNode))
WHERE none(n IN nodes(p) WHERE coalesce(n.type, '') IN ['Long', 'Integer', 'int', 'long'])
RETURN p AS path

UNION ALL

CALL () {
  MATCH (c:Call)
  WHERE
    (
      c.methodFullName IS NOT NULL AND (
        toLower(c.methodFullName) CONTAINS 'org.thymeleaf.' OR
        toLower(c.methodFullName) CONTAINS 'templateengine.process' OR
        toLower(c.methodFullName) CONTAINS 'itemplateengine.process'
      )
    ) OR (
      any(sel IN coalesce(c.selectors, []) WHERE sel IN ['process', 'processThrottled']) AND (
        any(rt IN coalesce(c.receiverTypes, []) WHERE
          toLower(rt) CONTAINS 'thymeleaf' OR
          rt IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
        ) OR
        any(rc IN coalesce(c.receivers, []) WHERE
          toLower(rc) CONTAINS 'thymeleaf' OR
          rc IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
        )
      )
    )
  RETURN count(c) AS thymeleafCallTotal
}
CALL () {
  MATCH (d:PomDependency|GradleDependency)
  RETURN count(d) AS depTotal
}
CALL () {
  MATCH (t:PomDependency|GradleDependency)
  WHERE
    toLower(coalesce(t.groupId, '')) = 'org.springframework.boot' AND
    toLower(coalesce(t.artifactId, '')) = 'spring-boot-starter-thymeleaf'
  RETURN count(t) AS thymeleafDep
}
WITH thymeleafCallTotal, depTotal, thymeleafDep

MATCH (sourceNode)-[:ARG]->(m:Method)
WHERE
  any(l IN labels(sourceNode) WHERE l IN [
    'DubboServiceArg', 'JsfXhtmlArg', 'JaxwsArg', 'StrutsActionArg', 'ThriftHandlerArg',
    'NettyHandlerArg', 'JfinalControllerArg', 'JbootControllerArg', 'SpringControllerArg',
    'SolonControllerArg', 'SpringInterceptorArg', 'JspServiceArg', 'WebServletArg',
    'WebXmlServletArg', 'WebXmlFilterArg', 'JaxrsArg', 'HttpHandlerArg'
  ])
  AND NOT coalesce(sourceNode.type, '') IN ['Long', 'Integer', 'HttpServletResponse', 'int', 'long']
  AND (
    NOT sourceNode:SpringControllerArg OR (
      NOT any(a IN coalesce(sourceNode.classAnnotations, []) WHERE
        a = 'RestController' OR toLower(a) ENDS WITH '.restcontroller'
      )
      AND NOT any(a IN coalesce(sourceNode.methodAnnotations, []) WHERE
        a = 'ResponseBody' OR toLower(a) ENDS WITH '.responsebody'
      )
    )
  )
  AND (
    exists {
      MATCH (m)-[:HAS_CALL]->(tc:Call)
      WHERE
        (
          tc.methodFullName IS NOT NULL AND (
            toLower(tc.methodFullName) CONTAINS 'org.thymeleaf.' OR
            toLower(tc.methodFullName) CONTAINS 'templateengine.process' OR
            toLower(tc.methodFullName) CONTAINS 'itemplateengine.process'
          )
        ) OR (
          any(sel IN coalesce(tc.selectors, []) WHERE sel IN ['process', 'processThrottled']) AND (
            any(rt IN coalesce(tc.receiverTypes, []) WHERE
              toLower(rt) CONTAINS 'thymeleaf' OR
              rt IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
            ) OR
            any(rc IN coalesce(tc.receivers, []) WHERE
              toLower(rc) CONTAINS 'thymeleaf' OR
              rc IN ['TemplateEngine', 'ITemplateEngine', 'org.thymeleaf.TemplateEngine', 'org.thymeleaf.ITemplateEngine']
            )
          )
        )
    } OR (
      thymeleafCallTotal = 0 AND (
        toLower(coalesce(m.fullName, '')) CONTAINS 'thymeleaf' OR
        toLower(coalesce(m.name, '')) CONTAINS 'thymeleaf'
      )
    )
  )
  AND (depTotal = 0 OR thymeleafDep > 0)

MATCH (m)-[:ARG]->(sinkNode:ReturnArg)
WHERE sinkNode.type = 'String'

MATCH p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*..12]->(sinkNode))
WHERE none(n IN nodes(p) WHERE coalesce(n.type, '') IN ['Long', 'Integer', 'int', 'long'])
RETURN p AS path
