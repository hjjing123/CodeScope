import better.files.{File => BFile}
import io.shiftleft.semanticcpg.language._
import scala.util.Try
import scala.language.reflectiveCalls
import java.nio.file.{Files, Paths}

@main def exec(
  cpgFile: String = "",
  outDir: String = "",
  ENABLE_CALLS: String = "",
  ENABLE_REF: String   = "",
  AST_MODE: String     = "",  // none | local | wide
  ARRAY_DELIM: String  = ""
): Unit = {

  def pickArg(v: String, k: String): String = {
    val p = Option(v).map(_.trim).getOrElse("")
    if (p.nonEmpty) p
    else {
      Option(System.getProperty(k)).map(_.trim).filter(_.nonEmpty)
        .orElse(sys.env.get(k).map(_.trim).filter(_.nonEmpty))
        .orElse(sys.env.get(k.toUpperCase).map(_.trim).filter(_.nonEmpty))
        .orElse(sys.env.get(k.toLowerCase).map(_.trim).filter(_.nonEmpty))
        .getOrElse("")
    }
  }

  val cpgFileVal = pickArg(cpgFile, "cpgFile")
  val outDirVal = pickArg(outDir, "outDir")
  val enableCalls = pickArg(ENABLE_CALLS, "ENABLE_CALLS").equalsIgnoreCase("true")
  val enableRef   = pickArg(ENABLE_REF, "ENABLE_REF").equalsIgnoreCase("true")
  val astMode     = pickArg(AST_MODE, "AST_MODE").toLowerCase match {
    case "none" | "local" | "wide" => pickArg(AST_MODE, "AST_MODE").toLowerCase
    case _ => "local"
  }
  val arrayDelimRaw = pickArg(ARRAY_DELIM, "ARRAY_DELIM")
  val arrayDelim = arrayDelimRaw match {
    case "001" | "\\001" | "\\u0001" | "\u0001" => "\u0001"
    case other if Option(other).exists(_.nonEmpty) => other
    case _ => "\u0001"
  }

  val cpgFileFinal = cpgFileVal
  val outDirFinal = outDirVal
  val cpgFilePath = cpgFileFinal.replace("\\", "/")
  val outDirPath = outDirFinal.replace("\\", "/")

  if (cpgFileFinal.isEmpty || outDirFinal.isEmpty) {
    println("missing cpgFile/outDir")
    return
  }

  val cpgOpt = Try(importCpg(cpgFilePath, "cpg", true)).toOption.flatten
  if (cpgOpt.isEmpty) {
    println("import cpg failed")
    return
  }
  val cpg = cpgOpt.get

  val out = BFile(outDirPath).createDirectories()

  def esc(s: String): String =
    "\"" + Option(s).getOrElse("").replace("\"", "\"\"").replace("\r\n", "\n") + "\""
  def simpleType(t: String): String = {
    val s = Option(t).getOrElse("")
    val noArr = if (s.endsWith("[]")) s.dropRight(2) else s
    val parts = noArr.split("[\\./$]").filter(_.nonEmpty)
    if (parts.nonEmpty) parts.last else noArr
  }
  def arr(values: Seq[String]): String =
    values.filter(_.nonEmpty).distinct.mkString(arrayDelim)
  def labelStr(values: Iterable[String]): String =
    values.filter(_.nonEmpty).toSeq.distinct.mkString(";")
  def iAny(v: Any): Int = v match {
    case o: Option[_] =>
      o.flatMap {
        case i: Integer => Some(i.intValue())
        case i: Int => Some(i)
        case _ => None
      }.getOrElse(-1)
    case i: Integer => i.intValue()
    case i: Int => i
    case _ => -1
  }
  def lineNum(n: AnyRef): Int =
    iAny(Try(n.asInstanceOf[{ def lineNumber: Any }].lineNumber).toOption.getOrElse(None))
  def colNum(n: AnyRef): Int =
    iAny(Try(n.asInstanceOf[{ def columnNumber: Any }].columnNumber).toOption.getOrElse(None))
  def nameStr(n: AnyRef): String =
    Try(n.asInstanceOf[{ def name: String }].name).toOption.getOrElse("")
  def typeFullNameStr(n: AnyRef): String =
    Try(n.asInstanceOf[{ def typeFullName: String }].typeFullName).toOption.getOrElse("")
  def typeStr(n: AnyRef): String = simpleType(typeFullNameStr(n))
  def codeStr(n: AnyRef): String =
    Try(n.asInstanceOf[{ def code: String }].code).toOption.getOrElse("")
  def contentStr(n: AnyRef): String =
    Try(n.asInstanceOf[{ def content: String }].content).toOption.getOrElse("")
  def isFieldIdentifier(n: AnyRef): Boolean =
    Try(n.getClass.getSimpleName).toOption.getOrElse("") == "FieldIdentifier"
  def receiverType(c: Call): String = {
    val v1 = Try(c.asInstanceOf[{ def receiverTypeFullName: String }].receiverTypeFullName).toOption.getOrElse("")
    if (v1.nonEmpty) v1
    else {
      Try(c.asInstanceOf[{ def receiver: Any }].receiver).toOption match {
        case Some(it: Iterator[_]) =>
          it.toList.headOption match {
            case Some(r: AnyRef) =>
              Try(r.asInstanceOf[{ def typeFullName: String }].typeFullName).toOption.getOrElse("")
            case _ => ""
          }
        case Some(it: Iterable[_]) =>
          it.headOption match {
            case Some(r: AnyRef) =>
              Try(r.asInstanceOf[{ def typeFullName: String }].typeFullName).toOption.getOrElse("")
            case _ => ""
          }
        case _ => ""
      }
    }
  }
  def uid(kind: String, file: String, line: Int, col: Int, extra: String): String =
    s"$kind|$file|$line|$col|$extra"
  def methodNameOf(m: Method): String = Option(m.name).getOrElse("")
  def methodFullNameOf(m: Method): String = Option(m.fullName).getOrElse("")
  def selectorsOf(c: Call): String = arr(Seq(Option(c.name).getOrElse("")))
  def receiverTypesOf(c: Call): String = {
    val rt = receiverType(c)
    val mf = Option(c.methodFullName).getOrElse("")
    val mfNoSig = if (mf.contains(":")) mf.substring(0, mf.indexOf(":")) else mf
    val clsFull = if (mfNoSig.contains(".")) mfNoSig.substring(0, mfNoSig.lastIndexOf(".")) else ""
    val tf = Try(c.asInstanceOf[{ def typeFullName: String }].typeFullName).toOption.getOrElse("")
    val simple = simpleType(rt)
    val simple2 = simpleType(clsFull)
    val simple3 = simpleType(tf)
    arr(Seq(rt, simple, clsFull, simple2, tf, simple3).filter(x => x.nonEmpty && x != "<unresolvedNamespace>").distinct)
  }
  def allocationClassName(c: Call): String = {
    val mf = Option(c.methodFullName).getOrElse("")
    val mfNoSig = if (mf.contains(":")) mf.substring(0, mf.indexOf(":")) else mf
    if (mfNoSig.endsWith(".<init>")) {
      val clsFull = mfNoSig.substring(0, mfNoSig.lastIndexOf("."))
      simpleType(clsFull)
    } else ""
  }
  def mergeAnnotations(names: Seq[String], fulls: Seq[String]): Seq[String] = {
    val simpleFulls = fulls.map(simpleType)
    (names ++ fulls ++ simpleFulls).filter(_.nonEmpty).distinct
  }
  def methodAnnotationsOf(m: Method): Seq[String] = {
    val names = Try(m.annotation.name.l).toOption.getOrElse(Nil)
    val fulls = Try(m.annotation.fullName.l).toOption.getOrElse(Nil)
    mergeAnnotations(names, fulls)
  }
  def classAnnotationsOf(m: Method): Seq[String] = {
    val names = Try(m.typeDecl.annotation.name.l).toOption.getOrElse(Nil)
    val fulls = Try(m.typeDecl.annotation.fullName.l).toOption.getOrElse(Nil)
    mergeAnnotations(names, fulls)
  }
  def paramAnnotationsOf(p: MethodParameterIn): Seq[String] = {
    val names = Try(p.annotation.name.l).toOption.getOrElse(Nil)
    val fulls = Try(p.annotation.fullName.l).toOption.getOrElse(Nil)
    mergeAnnotations(names, fulls)
  }
  def flatArgsOf(p: MethodParameterIn): Seq[String] = {
    val tfn = Option(p.typeFullName).getOrElse("")
    if (tfn.isEmpty) Nil
    else {
      val tds = Try(cpg.typeDecl.l).toOption.getOrElse(Nil)
      val td = tds.find(td => Option(td.fullName).contains(tfn) || Option(td.name).contains(simpleType(tfn)))
      td.map(t => Try(t.member.name.l).toOption.getOrElse(Nil)).getOrElse(Nil)
    }
  }
  def paramIndexOf(p: MethodParameterIn): Int = {
    val idx = iAny(Try(p.asInstanceOf[{ def index: Any }].index).toOption.getOrElse(None))
    if (idx >= 0) idx
    else iAny(Try(p.asInstanceOf[{ def order: Any }].order).toOption.getOrElse(None))
  }
  def mkVarRow(id: String, name: String, vtype: String, vmethod: String, file: String, line: Int, col: Int, code: String, segLabels: String, classAnns: Seq[String], methodAnns: Seq[String], paramAnns: Seq[String], flatArgs: Seq[String], declKind: String, assignRight: String, paramIndex: Int): String =
    s"${esc(id)},${esc("Var")},${esc(name)},${esc(vtype)},${esc(vmethod)},${esc(file)},$line,$col,${esc(code)},${esc(segLabels)},${esc(arr(classAnns))},${esc(arr(methodAnns))},${esc(arr(paramAnns))},${esc(arr(flatArgs))},${esc(declKind)},${esc(assignRight)},$paramIndex,${esc("Var")}" 
  def trimQuotes(v: String): String = {
    val s = Option(v).map(_.trim).getOrElse("")
    if ((s.startsWith("\"") && s.endsWith("\"") && s.length >= 2) || (s.startsWith("'") && s.endsWith("'") && s.length >= 2)) s.substring(1, s.length - 1)
    else s
  }
  def lineAt(content: String, idx: Int): Int = {
    if (idx <= 0) 1 else content.substring(0, idx).count(_ == '\n') + 1
  }
  def parseProperties(content: String): Seq[(String, String, Int, String)] = {
    val lines = content.split("\n", -1)
    val out = scala.collection.mutable.ArrayBuffer[(String, String, Int, String)]()
    var i = 0
    while (i < lines.length) {
      val raw = lines(i)
      val t = raw.trim
      if (t.nonEmpty && !t.startsWith("#") && !t.startsWith("!")) {
        val m = t.split("=|:", 2)
        if (m.length == 2) {
          val key = m(0).trim
          val value = trimQuotes(m(1))
          if (key.nonEmpty) out += ((key, value, i + 1, raw))
        }
      }
      i += 1
    }
    out.toSeq
  }
  def parseYaml(content: String): Seq[(String, String, Int, String)] = {
    val lines = content.split("\n", -1)
    val out = scala.collection.mutable.ArrayBuffer[(String, String, Int, String)]()
    val stack = scala.collection.mutable.ArrayBuffer[(Int, String)]()
    var i = 0
    while (i < lines.length) {
      val raw = lines(i)
      val trimmed = raw.trim
      if (trimmed.nonEmpty && !trimmed.startsWith("#") && !trimmed.startsWith("-")) {
        val indent = raw.takeWhile(c => c == ' ' || c == '\t').length
        val parts = trimmed.split(":", 2)
        val key = parts(0).trim
        val value = if (parts.length == 2) trimQuotes(parts(1)) else ""
        while (stack.nonEmpty && stack.last._1 >= indent) stack.remove(stack.length - 1)
        if (value.isEmpty) {
          if (key.nonEmpty) stack += ((indent, key))
        } else {
          val path = (stack.map(_._2) :+ key).mkString(".")
          if (path.nonEmpty) out += ((path, value, i + 1, raw))
        }
      }
      i += 1
    }
    out.toSeq
  }
  def parseXml(content: String): Seq[(String, String, String, Int, String)] = {
    val out = scala.collection.mutable.ArrayBuffer[(String, String, String, Int, String)]()
    val seen = scala.collection.mutable.HashSet[String]()
    def add(name: String, value: String, innerText: String, ln: Int, raw: String): Unit = {
      val n = Option(name).map(_.trim).getOrElse("")
      val v = Option(value).map(_.trim).getOrElse("")
      val t = Option(innerText).map(_.trim).getOrElse("")
      if (n.nonEmpty) {
        val key = s"$n|$v|$t|$ln"
        if (!seen.contains(key)) {
          out += ((n, v, t, ln, raw))
          seen.add(key)
        }
      }
    }
    val rText = "(?s)<([A-Za-z0-9_:\\-\\.]+)(\\s[^>]*)?>([^<]*)</\\1>".r
    rText.findAllMatchIn(content).foreach { m =>
      val name = Option(m.group(1)).map(_.trim).getOrElse("")
      val value = Option(m.group(3)).map(_.trim).getOrElse("")
      val ln = lineAt(content, m.start)
      val raw = m.group(0).replace("\r\n", "\n")
      add(name, value, value, ln, raw)
    }
    val rTag = "(?s)<(?!/)([A-Za-z0-9_:\\-\\.]+)(\\s[^>]*?)?>".r
    val rAttrD = "([A-Za-z0-9_:\\-\\.]+)\\s*=\\s*\"([^\"]*)\"".r
    val rAttrS = "([A-Za-z0-9_:\\-\\.]+)\\s*=\\s*'([^']*)'".r
    val rAttrU = "([A-Za-z0-9_:\\-\\.]+)\\s*=\\s*([^\\s\"'>/]+)".r
    rTag.findAllMatchIn(content).foreach { m =>
      val attrStr = Option(m.group(2)).getOrElse("")
      if (attrStr.nonEmpty) {
        val attrs = scala.collection.mutable.LinkedHashMap[String, String]()
        rAttrD.findAllMatchIn(attrStr).foreach { mm => attrs.update(mm.group(1), mm.group(2)) }
        rAttrS.findAllMatchIn(attrStr).foreach { mm => if (!attrs.contains(mm.group(1))) attrs.update(mm.group(1), mm.group(2)) }
        rAttrU.findAllMatchIn(attrStr).foreach { mm => if (!attrs.contains(mm.group(1))) attrs.update(mm.group(1), mm.group(2)) }
        val ln = lineAt(content, m.start)
        val raw = m.group(0).replace("\r\n", "\n")
        attrs.foreach { case (k, v) => add(k, trimQuotes(v), "", ln, raw) }
        val nameAttr = trimQuotes(attrs.getOrElse("name", ""))
        val valueAttr = trimQuotes(attrs.getOrElse("value", ""))
        if (nameAttr.nonEmpty && valueAttr.nonEmpty) add(nameAttr, valueAttr, "", ln, raw)
      }
    }
    out.toSeq
  }
  def parseMybatisPlaceholders(content: String): Seq[(String, String, String, String, Int, String)] = {
    val namespace = """(?s)<mapper[^>]*namespace\s*=\s*['\"]([^'\"]+)['\"][^>]*>""".r.findFirstMatchIn(content).map(_.group(1).trim).getOrElse("")
    if (namespace.isEmpty) return Nil
    val out = scala.collection.mutable.ArrayBuffer[(String, String, String, String, Int, String)]()
    val stmtRe = """(?s)<(select|update|insert|delete)\b([^>]*)>(.*?)</\1>""".r
    val idRe = """id\s*=\s*['\"]([^'\"]+)['\"]""".r
    val phRe = """\$\{([^}]+)\}""".r
    stmtRe.findAllMatchIn(content).foreach { m =>
      val stmtType = Option(m.group(1)).map(_.trim).getOrElse("")
      val attrs = Option(m.group(2)).getOrElse("")
      val body = Option(m.group(3)).getOrElse("")
      val block = m.group(0).replace("\r\n", "\n")
      val stmtId = idRe.findFirstMatchIn(attrs).map(_.group(1).trim).getOrElse("")
      if (stmtType.nonEmpty && stmtId.nonEmpty) {
        val ln = lineAt(content, m.start)
        phRe.findAllMatchIn(body).foreach { mm =>
          val expr = Option(mm.group(1)).map(_.trim).getOrElse("")
          if (expr.nonEmpty) out += ((namespace, stmtId, stmtType, expr, ln, block))
        }
      }
    }
    out.toSeq.distinct
  }
  def normalizePath(p: String): String =
    Option(p).getOrElse("").replace("\\", "/")
  def isConfigLikeFile(path: String): Boolean = {
    val p = normalizePath(path).toLowerCase
    p.endsWith(".properties") ||
    p.endsWith(".yml") ||
    p.endsWith(".yaml") ||
    p.endsWith(".xml") ||
    p.endsWith("build.gradle") ||
    p.endsWith("build.gradle.kts")
  }
  val ignoredPathSegments = Set(".git", ".idea", "target", "build", "node_modules", "dist", "out")
  def isIgnoredPath(path: String): Boolean = {
    val p = normalizePath(path).toLowerCase
    p.split("/").exists(seg => ignoredPathSegments.contains(seg))
  }
  def isSourceLikeFile(path: String): Boolean = {
    val p = normalizePath(path).toLowerCase
    p.endsWith(".java") ||
    p.endsWith(".kt") ||
    p.endsWith(".kts") ||
    p.endsWith(".jsp") ||
    p.endsWith(".jspx")
  }
  def suffixMatchScore(candidate: String, tail: String): Int = {
    val cSeg = normalizePath(candidate).toLowerCase.split("/").filter(_.nonEmpty)
    val tSeg = normalizePath(tail).toLowerCase.split("/").filter(_.nonEmpty)
    val max = Math.min(cSeg.length, tSeg.length)
    var i = 1
    var score = 0
    while (i <= max && cSeg(cSeg.length - i) == tSeg(tSeg.length - i)) {
      score += 1
      i += 1
    }
    score
  }
  val scanRoots: Seq[String] = {
    val roots = scala.collection.mutable.ArrayBuffer[String]()
    def addRoot(p: String): Unit = {
      val n = normalizePath(p).trim
      if (n.nonEmpty && !roots.contains(n)) roots += n
    }
    val explicitKeys = Seq("SOURCE_ROOT", "SCAN_ROOT", "CODE_ROOT")
    explicitKeys.foreach { k =>
      sys.env.get(k).foreach(addRoot)
      Option(System.getProperty(k)).foreach(addRoot)
    }
    val cpgPathObj = Try(Paths.get(cpgFilePath)).toOption
    cpgPathObj.foreach { cp =>
      Option(cp.getParent).foreach { cpgDir =>
        val binName = Option(cp.getFileName).map(_.toString).getOrElse("")
        val projectName = if (binName.toLowerCase.endsWith(".bin")) binName.dropRight(4) else binName
        Option(cpgDir.getParent).foreach { ws =>
          val codeRoot = ws.resolve("code")
          if (projectName.nonEmpty) {
            val codeProj = codeRoot.resolve(projectName)
            if (Files.isDirectory(codeProj)) addRoot(codeProj.toString)
          }
          if (roots.isEmpty && Files.isDirectory(codeRoot)) addRoot(codeRoot.toString)
          if (roots.isEmpty) addRoot(ws.toString)
        }
        if (roots.isEmpty) addRoot(cpgDir.toString)
      }
    }
    roots.toSeq.distinct
  }
  val localConfigFiles: Seq[String] = {
    val rows = scala.collection.mutable.ArrayBuffer[String]()
    scanRoots.foreach { r =>
      val root = Try(Paths.get(r)).toOption
      root.filter(Files.isDirectory(_)).foreach { rp =>
        val stream = Try(Files.walk(rp)).toOption
        stream.foreach { st =>
          try {
            val it = st.iterator()
            while (it.hasNext) {
              val fp = it.next()
              if (Files.isRegularFile(fp)) {
                val p = normalizePath(fp.toString)
                if (isConfigLikeFile(p) && !isIgnoredPath(p)) rows += p
              }
            }
          } finally {
            Try(st.close())
          }
        }
      }
    }
    rows.distinct.toSeq
  }
  val localSourceFiles: Seq[String] = {
    val rows = scala.collection.mutable.ArrayBuffer[String]()
    scanRoots.foreach { r =>
      val root = Try(Paths.get(r)).toOption
      root.filter(Files.isDirectory(_)).foreach { rp =>
        val stream = Try(Files.walk(rp)).toOption
        stream.foreach { st =>
          try {
            val it = st.iterator()
            while (it.hasNext) {
              val fp = it.next()
              if (Files.isRegularFile(fp)) {
                val p = normalizePath(fp.toString)
                if (isSourceLikeFile(p) && !isIgnoredPath(p)) rows += p
              }
            }
          } finally {
            Try(st.close())
          }
        }
      }
    }
    rows.distinct.toSeq
  }
  val localConfigByName: Map[String, Seq[String]] = {
    val m = scala.collection.mutable.Map[String, scala.collection.mutable.ArrayBuffer[String]]()
    localConfigFiles.foreach { p =>
      val name = normalizePath(p).toLowerCase.split("/").lastOption.getOrElse("")
      if (name.nonEmpty) {
        val bucket = m.getOrElseUpdate(name, scala.collection.mutable.ArrayBuffer[String]())
        bucket += p
      }
    }
    m.map { case (k, v) => k -> v.toSeq.distinct }.toMap
  }
  val localSourceByName: Map[String, Seq[String]] = {
    val m = scala.collection.mutable.Map[String, scala.collection.mutable.ArrayBuffer[String]]()
    localSourceFiles.foreach { p =>
      val name = normalizePath(p).toLowerCase.split("/").lastOption.getOrElse("")
      if (name.nonEmpty) {
        val bucket = m.getOrElseUpdate(name, scala.collection.mutable.ArrayBuffer[String]())
        bucket += p
      }
    }
    m.map { case (k, v) => k -> v.toSeq.distinct }.toMap
  }
  val localSourceSet: Set[String] = localSourceFiles.map(normalizePath).toSet
  def isTrackedCodeFile(path: String): Boolean = {
    val p = normalizePath(path)
    p.nonEmpty && (localSourceSet.contains(p) || isConfigLikeFile(p))
  }
  def sourcePathTails(path: String): Seq[String] = {
    val lower = normalizePath(path).toLowerCase
    val tailFromTmp = ".*/jimple2cpg-[^/]+/(.*)".r.findFirstMatchIn(lower).map(_.group(1)).getOrElse("")
    val rawTails = Seq(lower, tailFromTmp).filter(_.nonEmpty).distinct
    rawTails.flatMap { t =>
      val alt = Seq(t, t.replace(".class", ".java"), t.replace(".class", ".kt"))
      alt.flatMap { item =>
        val seg = item.split("/").filter(_.nonEmpty)
        val last2 = if (seg.length >= 2) Seq(seg.takeRight(2).mkString("/")) else Nil
        val last3 = if (seg.length >= 3) Seq(seg.takeRight(3).mkString("/")) else Nil
        val srcMainJava = item.split("/src/main/java/").lift(1).toSeq
        val srcTestJava = item.split("/src/test/java/").lift(1).toSeq
        Seq(item) ++ last2 ++ last3 ++ srcMainJava ++ srcTestJava
      }
    }.filter(_.nonEmpty).distinct
  }
  def resolveSourcePath(path: String): String = {
    val p = normalizePath(path).trim
    if (p.isEmpty) ""
    else {
      val direct = Try(BFile(p)).toOption.filter(_.isRegularFile).map(f => normalizePath(f.path.toString)).getOrElse("")
      if (direct.nonEmpty) direct
      else {
        val baseName = normalizePath(p).toLowerCase.split("/").lastOption.getOrElse("").replace(".class", ".java")
        val candidates = localSourceByName.getOrElse(baseName, Nil)
        if (candidates.isEmpty) ""
        else {
          val tails = sourcePathTails(p)
          val ranked = candidates.map { c =>
            val cl = normalizePath(c).toLowerCase
            val suffix = tails.map(t => suffixMatchScore(cl, t)).foldLeft(0)((a, b) => Math.max(a, b))
            val srcBonus = if (cl.contains("/src/main/java/")) 2 else if (cl.contains("/src/test/java/")) 1 else 0
            val score = suffix * 10 + srcBonus
            (c, score, cl.length)
          }.sortBy(x => (-x._2, x._3))
          if (ranked.nonEmpty && ranked.head._2 > 0) ranked.head._1 else ""
        }
      }
    }
  }
  def resolveContentPath(path: String): String = {
    val p = normalizePath(path).trim
    if (p.isEmpty) ""
    else {
      val direct = Try(BFile(p)).toOption.filter(_.isRegularFile).map(f => normalizePath(f.path.toString)).getOrElse("")
      if (direct.nonEmpty) direct
      else {
        val lower = p.toLowerCase
        val name = lower.split("/").lastOption.getOrElse("")
        val candidates = localConfigByName.getOrElse(name, Nil)
        if (candidates.isEmpty) ""
        else {
          val tailFromTmp = ".*/jimple2cpg-[^/]+/(.*)".r.findFirstMatchIn(lower).map(_.group(1)).getOrElse("")
          val rawTails = Seq(lower, tailFromTmp).filter(_.nonEmpty).distinct
          val tails = rawTails.flatMap { t =>
            val seg = t.split("/").filter(_.nonEmpty)
            val last2 = if (seg.length >= 2) Seq(seg.takeRight(2).mkString("/")) else Nil
            val last3 = if (seg.length >= 3) Seq(seg.takeRight(3).mkString("/")) else Nil
            val bootDrop = if (t.startsWith("boot-inf/classes/")) Seq(t.stripPrefix("boot-inf/classes/")) else Nil
            val mavenPom = if (t.startsWith("meta-inf/maven/") && t.endsWith("/pom.xml")) Seq("pom.xml") else Nil
            Seq(t) ++ last2 ++ last3 ++ bootDrop ++ mavenPom
          }.filter(_.nonEmpty).distinct
          val ranked = candidates.map { c =>
            val cl = normalizePath(c).toLowerCase
            val suffix = tails.map(t => suffixMatchScore(cl, t)).foldLeft(0)((a, b) => Math.max(a, b))
            val srcBonus = if (cl.contains("/src/main/resources/")) 2 else 0
            val srcBonus2 = if (cl.contains("/src/main/")) 1 else 0
            val buildPenalty = if (cl.contains("/target/") || cl.contains("/build/") || cl.contains("/boot-inf/")) 1 else 0
            val score = suffix * 10 + srcBonus + srcBonus2 - buildPenalty
            (c, score, cl.length)
          }.sortBy(x => (-x._2, x._3))
          if (ranked.nonEmpty && ranked.head._2 > 0) ranked.head._1 else ""
        }
      }
    }
  }
  def readContent(path: String, raw: String): String = {
    if (raw.nonEmpty) raw
    else {
      val p = Option(path).map(_.trim).getOrElse("")
      if (p.nonEmpty) {
        val resolved = resolveContentPath(p)
        if (resolved.nonEmpty) Try(BFile(resolved)).toOption.filter(_.isRegularFile).map(_.contentAsString).getOrElse("")
        else ""
      }
      else ""
    }
  }
  def parsePom(content: String): (Map[String, String], Seq[(String, String, String, String, Int, String)]) = {
    val props = scala.collection.mutable.Map[String, String]()
    val propBlock = "(?s)<properties>(.*?)</properties>".r.findFirstMatchIn(content).map(_.group(1)).getOrElse("")
    "(?s)<([A-Za-z0-9_.-]+)>(.*?)</\\1>".r.findAllMatchIn(propBlock).foreach { m =>
      val k = m.group(1).trim
      val v = m.group(2).trim
      if (k.nonEmpty && v.nonEmpty) props.update(k, v)
    }
    def tagValue(block: String, tag: String): String =
      (s"(?s)<$tag>(.*?)</$tag>".r.findFirstMatchIn(block).map(_.group(1)).getOrElse("")).trim
    def resolveVersion(v: String): String =
      "\\$\\{([^}]+)\\}".r.findFirstMatchIn(v).map(_.group(1)).flatMap(props.get).getOrElse("")

    val depMgmtRanges = scala.collection.mutable.ArrayBuffer[(Int, Int, String)]()
    "(?s)<dependencyManagement>(.*?)</dependencyManagement>".r.findAllMatchIn(content).foreach { m =>
      depMgmtRanges += ((m.start, m.end, m.group(1)))
    }
    def inDepMgmt(pos: Int): Boolean = depMgmtRanges.exists { case (s, e, _) => pos >= s && pos <= e }

    val depMgmt = scala.collection.mutable.Map[(String, String), String]()
    depMgmtRanges.foreach { case (_, _, inner) =>
      "(?s)<dependency>(.*?)</dependency>".r.findAllMatchIn(inner).foreach { m =>
        val block = m.group(1)
        val groupId = tagValue(block, "groupId")
        val artifactId = tagValue(block, "artifactId")
        val version = tagValue(block, "version")
        if (groupId.nonEmpty && artifactId.nonEmpty && version.nonEmpty) {
          val resolved = resolveVersion(version)
          val realVersion = if (resolved.nonEmpty) resolved else version
          depMgmt.update((groupId, artifactId), realVersion)
        }
      }
    }
    val deps = scala.collection.mutable.ArrayBuffer[(String, String, String, String, Int, String)]()
    "(?s)<dependency>(.*?)</dependency>".r.findAllMatchIn(content).foreach { m =>
      if (inDepMgmt(m.start)) {
      } else {
      val block = m.group(1)
      val groupId = tagValue(block, "groupId")
      val artifactId = tagValue(block, "artifactId")
      val versionRaw = tagValue(block, "version")
      if (groupId.nonEmpty && artifactId.nonEmpty) {
        val version = if (versionRaw.nonEmpty) versionRaw else depMgmt.getOrElse((groupId, artifactId), "")
        val resolved = if (version.nonEmpty) resolveVersion(version) else ""
        val realVersion = if (resolved.nonEmpty) resolved else version
        val ln = lineAt(content, m.start)
        deps += ((groupId, artifactId, version, realVersion, ln, block))
      }
      }
    }
    (props.toMap, deps.toSeq)
  }

  def parseGradle(content: String): Seq[(String, String, String, String, Int, String)] = {
    val props = scala.collection.mutable.Map[String, String]()
    "(?s)ext\\s*\\{(.*?)\\}".r.findAllMatchIn(content).foreach { m =>
      val block = m.group(1)
      "(?m)^\\s*([A-Za-z0-9_.-]+)\\s*=\\s*['\"]([^'\"]+)['\"]".r.findAllMatchIn(block).foreach { mm =>
        props.update(mm.group(1).trim, mm.group(2).trim)
      }
    }
    "(?m)^\\s*(?:ext\\.)?([A-Za-z0-9_.-]+)\\s*=\\s*['\"]([^'\"]+)['\"]".r.findAllMatchIn(content).foreach { mm =>
      val k = mm.group(1).trim
      val v = mm.group(2).trim
      if (k.nonEmpty && v.nonEmpty) props.update(k, v)
    }

    def resolveVersion(v: String): String = {
      var out = v
      "\\$\\{([^}]+)\\}".r.findAllMatchIn(out).foreach { m =>
        props.get(m.group(1)).foreach { pv => out = out.replace(m.group(0), pv) }
      }
      "\\$([A-Za-z0-9_.-]+)".r.findAllMatchIn(out).foreach { m =>
        props.get(m.group(1)).foreach { pv => out = out.replace(m.group(0), pv) }
      }
      if (out.nonEmpty && out != v) out else ""
    }

    val configs = Set(
      "implementation","api","compile","compileOnly","runtimeOnly",
      "testImplementation","testCompile","testRuntimeOnly",
      "annotationProcessor","kapt","classpath","compileClasspath","runtimeClasspath"
    )

    val deps = scala.collection.mutable.ArrayBuffer[(String, String, String, String, Int, String)]()
    val lines = content.split("\n", -1)
    var i = 0
    while (i < lines.length) {
      val raw = lines(i)
      val line = raw.trim
      if (line.nonEmpty && !line.startsWith("//") && !line.startsWith("/*") && !line.startsWith("*")) {
        "^([A-Za-z0-9_]+)\\s*\\(?\\s*['\"]([^'\"]+)['\"]\\s*\\)?".r.findFirstMatchIn(line).foreach { m =>
          val cfg = m.group(1)
          val spec = m.group(2)
          if (configs.contains(cfg) && spec.contains(":")) {
            val parts = spec.split(":", -1)
            if (parts.length >= 2) {
              val g = parts(0).trim
              val a = parts(1).trim
              val v = if (parts.length >= 3) parts(2).trim else ""
              val rv = if (v.nonEmpty) resolveVersion(v) else ""
              val real = if (rv.nonEmpty) rv else v
              if (g.nonEmpty && a.nonEmpty) deps += ((g, a, v, real, i + 1, raw))
            }
          }
        }

        "^([A-Za-z0-9_]+)\\s+(.+)$".r.findFirstMatchIn(line).foreach { m =>
          val cfg = m.group(1)
          val rest = m.group(2)
          if (configs.contains(cfg)) {
            val g = "group\\s*:\\s*['\"]([^'\"]+)['\"]".r.findFirstMatchIn(rest).map(_.group(1)).getOrElse("")
            val a = "name\\s*:\\s*['\"]([^'\"]+)['\"]".r.findFirstMatchIn(rest).map(_.group(1)).getOrElse("")
            val v = "version\\s*:\\s*['\"]([^'\"]+)['\"]".r.findFirstMatchIn(rest).map(_.group(1)).getOrElse("")
            if (g.nonEmpty && a.nonEmpty) {
              val rv = if (v.nonEmpty) resolveVersion(v) else ""
              val real = if (rv.nonEmpty) rv else v
              deps += ((g, a, v, real, i + 1, raw))
            }
          }
        }
      }
      i += 1
    }
    deps.toSeq
  }

  def writeHeader(path: BFile, text: String): Unit = path.writeText(text)

  // ---------- output files ----------
  val nFileH = out / "nodes_File_header.csv"
  val nFileD = out / "nodes_File_data.csv"
  val nMethH = out / "nodes_Method_header.csv"
  val nMethD = out / "nodes_Method_data.csv"
  val nCallH = out / "nodes_Call_header.csv"
  val nCallD = out / "nodes_Call_data.csv"
  val nVarH  = out / "nodes_Var_header.csv"
  val nVarD  = out / "nodes_Var_data.csv"
  val nLitH  = out / "nodes_Lit_header.csv"
  val nLitD  = out / "nodes_Lit_data.csv"
  val nPropH = out / "nodes_PropertiesKeyValue_header.csv"
  val nPropD = out / "nodes_PropertiesKeyValue_data.csv"
  val nYmlH  = out / "nodes_YmlKeyValue_header.csv"
  val nYmlD  = out / "nodes_YmlKeyValue_data.csv"
  val nPomH  = out / "nodes_PomDependency_header.csv"
  val nPomD  = out / "nodes_PomDependency_data.csv"
  val nGradleH  = out / "nodes_GradleDependency_header.csv"
  val nGradleD  = out / "nodes_GradleDependency_data.csv"
  val nXmlH  = out / "nodes_XmlElement_header.csv"
  val nXmlD  = out / "nodes_XmlElement_data.csv"

  val eInFileH  = out / "edges_IN_FILE_header.csv"
  val eInFileD  = out / "edges_IN_FILE_data.csv"
  val eHasCallH = out / "edges_HAS_CALL_header.csv"
  val eHasCallD = out / "edges_HAS_CALL_data.csv"
  val eCallsH   = out / "edges_CALLS_header.csv"
  val eCallsD   = out / "edges_CALLS_data.csv"
  val eArgH     = out / "edges_ARG_header.csv"
  val eArgD     = out / "edges_ARG_data.csv"
  val eAstH     = out / "edges_AST_header.csv"
  val eAstD     = out / "edges_AST_data.csv"
  val eRefH     = out / "edges_REF_header.csv"
  val eRefD     = out / "edges_REF_data.csv"

  // Neo4j-admin CSV headers（id:ID 方便导入）
  writeHeader(nFileH, "id:ID,kind,name,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nMethH, "id:ID,kind,name,fullName,file,line:INT,col:INT,code,classAnnotations:STRING[],methodAnnotations:STRING[],paramTypes:STRING[],paramNames:STRING[],:LABEL\n")
  writeHeader(nCallH, "id:ID,kind,name,methodFullName,receiverType,selectors:STRING[],receiverTypes:STRING[],receivers:STRING[],AllocationClassName,method,ownerMethod,ownerMethodFullName,file,line:INT,col:INT,code,isThisReceiver:BOOLEAN,segLabels:STRING[],:LABEL\n")
  writeHeader(nVarH,  "id:ID,kind,name,type,method,file,line:INT,col:INT,code,segLabels:STRING[],classAnnotations:STRING[],methodAnnotations:STRING[],paramAnnotations:STRING[],flatArgs:STRING[],declKind,assignRight,paramIndex:INT,:LABEL\n")
  writeHeader(nLitH,  "id:ID,kind,type,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nPropH, "id:ID,kind,name,value,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nYmlH,  "id:ID,kind,name,value,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nPomH,  "id:ID,kind,groupId,artifactId,version,realVersion,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nGradleH,  "id:ID,kind,groupId,artifactId,version,realVersion,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nXmlH,  "id:ID,kind,qName,value,innerText,file,line:INT,col:INT,code,:LABEL\n")

  writeHeader(eInFileH,  ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eHasCallH, ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eCallsH,   ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eArgH,     ":START_ID,:END_ID,argIndex:INT,:TYPE\n")
  writeHeader(eAstH,     ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eRefH,     ":START_ID,:END_ID,:TYPE\n")

  // ---------- accumulators ----------
  val fileRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val methRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val callRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val varRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val litRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val propRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val ymlRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val pomRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val gradleRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val xmlRows  = scala.collection.mutable.LinkedHashMap[String, String]()

  val eInFile  = scala.collection.mutable.LinkedHashSet[String]()
  val eHasCall = scala.collection.mutable.LinkedHashSet[String]()
  val eCalls   = scala.collection.mutable.LinkedHashSet[String]()
  val eArg     = scala.collection.mutable.LinkedHashSet[String]()
  val eAst     = scala.collection.mutable.LinkedHashSet[String]()
  val eRef     = scala.collection.mutable.LinkedHashSet[String]()

  // ---------- semantics (Java) ----------
  def receiverNodes(c: Call): Seq[AnyRef] = {
    Try(c.asInstanceOf[{ def receiver: Any }].receiver).toOption match {
      case Some(it: Iterator[_]) => it.toList.collect { case r: AnyRef => r }
      case Some(it: Iterable[_]) => it.collect { case r: AnyRef => r }.toSeq
      case Some(r: AnyRef) => Seq(r)
      case _ => Nil
    }
  }

  def isThisNode(n: AnyRef): Boolean = {
    val cls = Try(n.getClass.getSimpleName).toOption.getOrElse("")
    if (cls == "This") true
    else {
      val name = Try(n.asInstanceOf[{ def name: String }].name).toOption.getOrElse("")
      val code = Try(n.asInstanceOf[{ def code: String }].code).toOption.getOrElse("")
      name == "this" || code == "this"
    }
  }

  def isThisReceiver(c: Call): Boolean = {
    receiverNodes(c).exists(isThisNode)
  }
  def receiverNamesOf(c: Call): String = {
    val names = receiverNodes(c).flatMap { r =>
      val name = Try(r.asInstanceOf[{ def name: String }].name).toOption.getOrElse("").trim
      val code = Try(r.asInstanceOf[{ def code: String }].code).toOption.getOrElse("").trim
      Seq(name, code).filter(_.nonEmpty)
    }.filterNot(_ == "this").distinct
    arr(names)
  }

  def isStaticMethod(m: Method): Boolean =
    Try(m.asInstanceOf[{ def isStatic: Boolean }].isStatic).toOption.getOrElse(false)

  def labelForCall(c: Call): Set[String] = {
    val labs = scala.collection.mutable.Set("Call")
    if (receiverNodes(c).nonEmpty) labs += "Receiver"
    if (isThisReceiver(c)) {
      labs += "ThisReference"
      labs += "Receiver"
    }
    labs.toSet
  }

  def labelForCallInMethod(c: Call, m: Method): Set[String] = {
    val labs = scala.collection.mutable.Set[String]() ++ labelForCall(c)
    if (receiverNodes(c).isEmpty && !isStaticMethod(m)) {
      labs += "ThisReference"
      labs += "Receiver"
    }
    labs.toSet
  }

  def isThisReceiverInMethod(c: Call, m: Method): Boolean = {
    val implicitThis = receiverNodes(c).isEmpty && !isStaticMethod(m)
    implicitThis || isThisReceiver(c)
  }

  def labelForParam(p: MethodParameterIn, owner: Method): Set[String] = {
    Set("Var","Param")
  }

  def callIdOf(c: Call, cf: String, cl: Int, cc: Int): String = {
    val base = s"${c.name}|${c.methodFullName}"
    if (cl < 0 || cc < 0) {
      val nid = Try(c.id).toOption.getOrElse(c.hashCode).toString
      uid("Call", cf, cl, cc, s"${base}|${nid}")
    } else {
      uid("Call", cf, cl, cc, base)
    }
  }
  def litIdOf(file: String, line: Int, col: Int, litTypeFullName: String, litCode: String, ownerMethodFullName: String): String = {
    val base = s"${litTypeFullName}|${litCode}"
    if (line < 0 || col < 0) uid("Lit", file, line, col, s"${base}|${ownerMethodFullName}")
    else uid("Lit", file, line, col, base)
  }

  // ---------- export FILE ----------
  cpg.file.l.foreach { f =>
    val fn = normalizePath(Option(f.name).getOrElse(""))
    if (isTrackedCodeFile(fn)) {
      val id = uid("File", fn, -1, -1, fn)
      fileRows.update(id, s"${esc(id)},${esc("File")},${esc(fn)},${esc(fn)},-1,-1,${esc("")},${esc("File")}")
    }
  }

  cpg.member.l.foreach { f =>
    val ff0 = Try(f.location.filename).toOption.getOrElse("")
    val ff = {
      val resolved = resolveSourcePath(ff0)
      if (resolved.nonEmpty) resolved else ff0
    }
    if (isTrackedCodeFile(ff)) {
      val fl = lineNum(f); val fc = colNum(f)
      val fname = nameStr(f)
      val ftype = simpleType(typeFullNameStr(f))
      val vid = uid("Var", ff, fl, fc, s"field|${fname}")
      val vset = scala.collection.mutable.Set("Var","FieldDeclaration","Decl")
      val segLabels = arr(vset.toSeq)
      varRows.update(vid, mkVarRow(vid, fname, ftype, "", ff, fl, fc, codeStr(f), segLabels, Nil, Nil, Nil, Nil, "Field", "", -1))
    }
  }

  localConfigFiles.foreach { rawPath =>
    val p = normalizePath(rawPath)
    val content = readContent(p, "")
    if (content.nonEmpty) {
      val fid = uid("File", p, -1, -1, p)
      fileRows.update(fid, s"${esc(fid)},${esc("File")},${esc(p)},${esc(p)},-1,-1,${esc("")},${esc("File")}")
      if (p.endsWith(".properties")) {
        parseProperties(content).foreach { case (k, v, ln, raw) =>
          val id = uid("PropertiesKeyValue", p, ln, 1, k)
          propRows.update(id, s"${esc(id)},${esc("PropertiesKeyValue")},${esc(k)},${esc(v)},${esc(p)},$ln,1,${esc(raw)},${esc("PropertiesKeyValue")}")
          eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
        }
      } else if (p.endsWith(".yml") || p.endsWith(".yaml")) {
        parseYaml(content).foreach { case (k, v, ln, raw) =>
          val id = uid("YmlKeyValue", p, ln, 1, k)
          ymlRows.update(id, s"${esc(id)},${esc("YmlKeyValue")},${esc(k)},${esc(v)},${esc(p)},$ln,1,${esc(raw)},${esc("YmlKeyValue")}")
          eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
        }
      } else if (p.endsWith("pom.xml")) {
        val (_, deps) = parsePom(content)
        deps.foreach { case (g, a, v, rv, ln, block) =>
          val id = uid("PomDependency", p, ln, 1, s"$g:$a:$v")
          pomRows.update(id, s"${esc(id)},${esc("PomDependency")},${esc(g)},${esc(a)},${esc(v)},${esc(rv)},${esc(p)},$ln,1,${esc(block)},${esc("PomDependency")}")
          eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
        }
      } else if (p.endsWith("build.gradle") || p.endsWith("build.gradle.kts")) {
        val deps = parseGradle(content)
        deps.foreach { case (g, a, v, rv, ln, block) =>
          val id = uid("GradleDependency", p, ln, 1, s"$g:$a:$v")
          gradleRows.update(id, s"${esc(id)},${esc("GradleDependency")},${esc(g)},${esc(a)},${esc(v)},${esc(rv)},${esc(p)},$ln,1,${esc(block)},${esc("GradleDependency")}")
          eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
        }
      } else if (p.endsWith(".xml")) {
        parseXml(content).foreach { case (q, v, t, ln, raw) =>
          val key = if (v.length > 80) v.take(80) else v
          val id = uid("XmlElement", p, ln, 1, s"$q:$key")
          xmlRows.update(id, s"${esc(id)},${esc("XmlElement")},${esc(q)},${esc(v)},${esc(t)},${esc(p)},$ln,1,${esc(raw)},${esc("XmlElement")}")
          eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
        }
        if (p.toLowerCase.contains("/mybatis/") || p.toLowerCase.contains("mapper.xml")) {
          parseMybatisPlaceholders(content).foreach { case (namespace, stmtId, stmtType, expr, ln, block) =>
            val id = uid("XmlElement", p, ln, 1, s"mybatis:$namespace#$stmtId#$expr")
            xmlRows.update(id, s"${esc(id)},${esc("XmlElement")},${esc("mybatis.placeholder")},${esc(expr)},${esc(s"$namespace#$stmtId#$stmtType")},${esc(p)},$ln,1,${esc(block)},${esc("XmlElement")}")
            eInFile.add(s"${esc(id)},${esc(fid)},IN_FILE")
          }
        }
      }
    }
  }

  // ---------- export METHOD + edges ----------
  cpg.method.l.foreach { m =>
    val mf0 = Try(m.location.filename).toOption.getOrElse("")
    val mf = {
      val resolved = resolveSourcePath(mf0)
      if (resolved.nonEmpty) resolved else mf0
    }
    if (isTrackedCodeFile(mf)) {
    val line = lineNum(m); val col = colNum(m)
    val mid  = uid("Method", mf, line, col, m.fullName)

    val mLabs = scala.collection.mutable.Set("Method")
    val mCode = Try(m.signature).toOption.getOrElse(m.name)
    val mClassAnns = classAnnotationsOf(m)
    val mMethodAnns = methodAnnotationsOf(m)
    val mParamTypes = arr(Try(m.parameter.l.map(p => simpleType(p.typeFullName))).toOption.getOrElse(Nil))
    val mParamNames = arr(Try(m.parameter.l.map(_.name)).toOption.getOrElse(Nil))

    methRows.update(mid, s"${esc(mid)},${esc("Method")},${esc(m.name)},${esc(m.fullName)},${esc(mf)},$line,$col,${esc(mCode)},${esc(arr(mClassAnns))},${esc(arr(mMethodAnns))},${esc(mParamTypes)},${esc(mParamNames)},${esc(labelStr(mLabs))}")

    val fid = uid("File", mf, -1, -1, mf)
    fileRows.update(fid, s"${esc(fid)},${esc("File")},${esc(mf)},${esc(mf)},-1,-1,${esc("")},${esc("File")}")
    eInFile.add(s"${esc(mid)},${esc(fid)},IN_FILE")

    if (enableCalls) {
      Try(m.callee.l).toOption.getOrElse(Nil).foreach { cal =>
        val cf0 = Try(cal.location.filename).toOption.getOrElse("")
        val cf = {
          val resolved = resolveSourcePath(cf0)
          if (resolved.nonEmpty) resolved else cf0
        }
        if (isTrackedCodeFile(cf)) {
          val cid = uid("Method", cf, lineNum(cal), colNum(cal), cal.fullName)
          eCalls.add(s"${esc(mid)},${esc(cid)},CALLS")
        }
      }
    }

    val hasGetRuntime = Try(m.call.name("getRuntime").l.nonEmpty).getOrElse(false)
    val hasProcessBuilderCtor = Try(m.call.l.exists { cc =>
      val mf = Option(cc.methodFullName).getOrElse("")
      val mfNoSig = if (mf.contains(":")) mf.substring(0, mf.indexOf(":")) else mf
      mfNoSig.endsWith(".<init>") && mfNoSig.contains("ProcessBuilder")
    }).getOrElse(false)

    val assignLeftIds = scala.collection.mutable.Set[String]()
    val assignRightByVar = scala.collection.mutable.Map[String, String]()
    Try(m.call.name("<operator>.assignment").l).toOption.getOrElse(Nil).foreach { ass =>
      val rhs = Try(ass.argument(2).code).toOption.getOrElse("")
      Try(ass.argument(1)).toOption.foreach { a =>
        val af0 = Try(a.location.filename).toOption.getOrElse(mf)
        val af = {
          val resolved = resolveSourcePath(af0)
          if (resolved.nonEmpty) resolved else af0
        }
        val al = lineNum(a); val ac = colNum(a)
        a match {
          case idn: Identifier =>
            val aid = uid("Var", af, al, ac, s"id|${idn.name}|${m.fullName}")
            assignLeftIds.add(aid)
            assignRightByVar.update(aid, rhs)
            val vset = scala.collection.mutable.Set("Var","Identifier","Reference","AssignLeft")
            val vtype = simpleType(idn.typeFullName)
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            varRows.update(aid, mkVarRow(aid, idn.name, vtype, vmethod, af, al, ac, codeStr(idn), segLabels, Nil, Nil, Nil, Nil, "Identifier", rhs, -1))
          case p: MethodParameterIn =>
            val aid = uid("Var", af, al, ac, s"param|${p.name}|${m.fullName}")
            assignLeftIds.add(aid)
            assignRightByVar.update(aid, rhs)
            val vset = scala.collection.mutable.Set[String]() ++ labelForParam(p, m)
            vset += "AssignLeft"
            val vtype = simpleType(p.typeFullName)
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            val pAnns = paramAnnotationsOf(p)
            val flat = flatArgsOf(p)
            varRows.update(aid, mkVarRow(aid, p.name, vtype, vmethod, af, al, ac, codeStr(p), segLabels, mClassAnns, mMethodAnns, pAnns, flat, "Param", rhs, paramIndexOf(p)))
          case l: Local =>
            val aid = uid("Var", af, al, ac, s"decl|${l.name}|${m.fullName}")
            assignLeftIds.add(aid)
            assignRightByVar.update(aid, rhs)
            val vset = scala.collection.mutable.Set("Var","Decl","LocalDeclaration","AssignLeft")
            val vtype = simpleType(l.typeFullName)
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            varRows.update(aid, mkVarRow(aid, l.name, vtype, vmethod, af, al, ac, codeStr(l), segLabels, Nil, Nil, Nil, Nil, "Local", rhs, -1))
          case other if isFieldIdentifier(other.asInstanceOf[AnyRef]) =>
            val aid = uid("Var", af, al, ac, s"field|${nameStr(other.asInstanceOf[AnyRef])}|${m.fullName}")
            assignLeftIds.add(aid)
            assignRightByVar.update(aid, rhs)
            val vset = scala.collection.mutable.Set("Var","FieldIdentifier","Reference","AssignLeft")
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            varRows.update(aid, mkVarRow(aid, nameStr(other.asInstanceOf[AnyRef]), "", vmethod, af, al, ac, codeStr(other.asInstanceOf[AnyRef]), segLabels, Nil, Nil, Nil, Nil, "FieldIdentifier", rhs, -1))
          case _ =>
        }
      }
    }

    m.local.l.foreach { l =>
      val lf0 = Try(l.location.filename).toOption.getOrElse(mf)
      val lf = {
        val resolved = resolveSourcePath(lf0)
        if (resolved.nonEmpty) resolved else lf0
      }
      val ll = lineNum(l); val lc = colNum(l)
      val vid = uid("Var", lf, ll, lc, s"decl|${l.name}|${m.fullName}")
      val vset = scala.collection.mutable.Set("Var","Decl","LocalDeclaration")
      val vtype = simpleType(l.typeFullName)
      val vmethod = methodNameOf(m)
      val segLabels = arr(vset.toSeq)
      val assignRight = assignRightByVar.getOrElse(vid, "")
      varRows.update(vid, mkVarRow(vid, l.name, vtype, vmethod, lf, ll, lc, codeStr(l), segLabels, Nil, Nil, Nil, Nil, "Local", assignRight, -1))
    }

    m.parameter.l.zipWithIndex.foreach { case (p, fallbackParamIndex) =>
      val pf0 = Try(p.location.filename).toOption.getOrElse(mf)
      val pf = {
        val resolved = resolveSourcePath(pf0)
        if (resolved.nonEmpty) resolved else pf0
      }
      val pl = lineNum(p); val pc = colNum(p)
      val pid = uid("Var", pf, pl, pc, s"param|${p.name}|${m.fullName}")
      val vset = scala.collection.mutable.Set[String]() ++ labelForParam(p, m)
      if (assignLeftIds.contains(pid)) vset += "AssignLeft"
      val vtype = simpleType(p.typeFullName)
      val vmethod = methodNameOf(m)
      val segLabels = arr(vset.toSeq)
      val pAnns = paramAnnotationsOf(p)
      val flat = flatArgsOf(p)
      val assignRight = assignRightByVar.getOrElse(pid, "")
      val paramIndex = {
        val raw = paramIndexOf(p)
        if (raw >= 0) raw else fallbackParamIndex
      }
      varRows.update(pid, mkVarRow(pid, p.name, vtype, vmethod, pf, pl, pc, codeStr(p), segLabels, mClassAnns, mMethodAnns, pAnns, flat, "Param", assignRight, paramIndex))
      eArg.add(s"${esc(pid)},${esc(mid)},-1,ARG")
    }

    // method 内 callsite
    m.call.l.foreach { c =>
      val cf0 = Try(c.location.filename).toOption.getOrElse(mf)
      val cf = {
        val resolved = resolveSourcePath(cf0)
        if (resolved.nonEmpty) resolved else cf0
      }
      if (isTrackedCodeFile(cf)) {
      val cl = lineNum(c); val cc = colNum(c)
      val cid = callIdOf(c, cf, cl, cc)

      val segLabels = arr(labelForCallInMethod(c, m).toSeq)
      val recvType = receiverType(c)
      val selectors = selectorsOf(c)
      val receiverTypesRaw = receiverTypesOf(c)
      val allocClsRaw = allocationClassName(c)
      val rtList0 = receiverTypesRaw.split(arrayDelim, -1).toSeq.filter(_.nonEmpty).filter(_ != "<unresolvedNamespace>")
      val rtList1 = {
        var s = rtList0
        if (Option(c.name).getOrElse("") == "exec" && !s.exists(_.contains("Runtime")) && hasGetRuntime) s = s :+ "Runtime"
        if (Option(c.name).getOrElse("") == "start" && !s.exists(_.contains("ProcessBuilder")) && hasProcessBuilderCtor) s = s :+ "ProcessBuilder"
        s.distinct
      }
      val receiverTypes = arr(rtList1)
      val receivers = receiverNamesOf(c)
      val allocCls = {
        var a = allocClsRaw
        if (a.isEmpty && Option(c.name).getOrElse("") == "start" && rtList1.exists(_.contains("ProcessBuilder"))) a = "ProcessBuilder"
        a
      }
      val mname = Option(c.name).getOrElse("")
      val ownerMethod = methodNameOf(m)
      val ownerMethodFullName = methodFullNameOf(m)

      val isThis = if (isThisReceiverInMethod(c, m)) "true" else "false"
      callRows.update(cid, s"${esc(cid)},${esc("Call")},${esc(c.name)},${esc(c.methodFullName)},${esc(recvType)},${esc(selectors)},${esc(receiverTypes)},${esc(receivers)},${esc(allocCls)},${esc(mname)},${esc(ownerMethod)},${esc(ownerMethodFullName)},${esc(cf)},$cl,$cc,${esc(codeStr(c))},${isThis},${esc(segLabels)},${esc("Call")}")
      eHasCall.add(s"${esc(mid)},${esc(cid)},HAS_CALL")

      c.argument.l.foreach { a =>
        val af0 = Try(a.location.filename).toOption.getOrElse(cf)
        val af = {
          val resolved = resolveSourcePath(af0)
          if (resolved.nonEmpty) resolved else af0
        }
        if (isTrackedCodeFile(af)) {
        val al = lineNum(a); val ac = colNum(a)
        val argIdx = Try(a.argumentIndex).toOption.getOrElse(-1)

        val (aid, kind, row) = a match {
          case p: MethodParameterIn =>
            val vid = uid("Var", af, al, ac, s"param|${p.name}|${m.fullName}")
            val vset = scala.collection.mutable.Set[String]() ++ labelForParam(p, m)
            vset += "CallArg"
            if (assignLeftIds.contains(vid)) vset += "AssignLeft"
            val segLabels = arr(vset.toSeq)
            val vtype = simpleType(p.typeFullName)
            val vmethod = methodNameOf(m)
            val pAnns = paramAnnotationsOf(p)
            val flat = flatArgsOf(p)
            val assignRight = assignRightByVar.getOrElse(vid, "")
            (vid, "Var", mkVarRow(vid, p.name, vtype, vmethod, af, al, ac, p.code, segLabels, mClassAnns, mMethodAnns, pAnns, flat, "Param", assignRight, paramIndexOf(p)))

          case l: Literal =>
            val lid = litIdOf(af, al, ac, l.typeFullName, l.code, m.fullName)
            val ltype = simpleType(l.typeFullName)
            (lid, "Lit", s"${esc(lid)},${esc("Lit")},${esc(ltype)},${esc(af)},$al,$ac,${esc(l.code)},${esc("Lit")}")

          case idn: Identifier =>
            val vid = uid("Var", af, al, ac, s"id|${idn.name}|${m.fullName}")
            val vset = scala.collection.mutable.Set("Var","Identifier","Reference","CallArg")
            if (assignLeftIds.contains(vid)) vset += "AssignLeft"
            if (enableRef) {
              Try(idn.refsTo.l).toOption.getOrElse(Nil).headOption.foreach { decl =>
                val df0 = Try(decl.location.filename).toOption.getOrElse(af)
                val df = {
                  val resolved = resolveSourcePath(df0)
                  if (resolved.nonEmpty) resolved else df0
                }
                val dl = lineNum(decl); val dc = colNum(decl)
                val dname = nameStr(decl)
                val dtype = simpleType(typeFullNameStr(decl))
                val dcode = codeStr(decl)
                val did = uid("Var", df, dl, dc, s"decl|${dname}|${m.fullName}")
                val dset = scala.collection.mutable.Set("Var","Decl")
                decl match {
                  case _: Local => dset += "LocalDeclaration"
                  case _ =>
                }
                val dmethod = methodNameOf(m)
                val segLabels = arr(dset.toSeq)
                val assignRight = assignRightByVar.getOrElse(did, "")
                val declKind = decl match {
                  case _: Local => "Local"
                  case _ => "Decl"
                }
                varRows.update(did, mkVarRow(did, dname, dtype, dmethod, df, dl, dc, dcode, segLabels, Nil, Nil, Nil, Nil, declKind, assignRight, -1))
                eRef.add(s"${esc(did)},${esc(vid)},REF")
              }
            }
            val vtype = simpleType(idn.typeFullName)
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            val assignRight = assignRightByVar.getOrElse(vid, "")
            (vid, "Var", mkVarRow(vid, idn.name, vtype, vmethod, af, al, ac, idn.code, segLabels, Nil, Nil, Nil, Nil, "Identifier", assignRight, -1))

          case other if isFieldIdentifier(other.asInstanceOf[AnyRef]) =>
            val aid = uid("Var", af, al, ac, s"field|${nameStr(other.asInstanceOf[AnyRef])}|${m.fullName}")
            val vset = scala.collection.mutable.Set("Var","FieldIdentifier","Reference","CallArg")
            if (assignLeftIds.contains(aid)) vset += "AssignLeft"
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            val assignRight = assignRightByVar.getOrElse(aid, "")
            (aid, "Var", mkVarRow(aid, nameStr(other.asInstanceOf[AnyRef]), "", vmethod, af, al, ac, codeStr(other.asInstanceOf[AnyRef]), segLabels, Nil, Nil, Nil, Nil, "FieldIdentifier", assignRight, -1))


          case cc2: Call =>
            val nid = callIdOf(cc2, af, al, ac)
            val segLabels2 = arr((labelForCall(cc2) + "CallArg").toSeq)
            val r2 = receiverType(cc2)
            val selectors2 = selectorsOf(cc2)
            val receiverTypes2 = receiverTypesOf(cc2)
            val allocCls2 = allocationClassName(cc2)
            val mname2 = Option(cc2.name).getOrElse("")
            val isThis2 = if (isThisReceiver(cc2)) "true" else "false"
            val receivers2 = receiverNamesOf(cc2)
            val ownerMethod2 = methodNameOf(m)
            val ownerMethodFullName2 = methodFullNameOf(m)
            (nid, "Call", s"${esc(nid)},${esc("Call")},${esc(cc2.name)},${esc(cc2.methodFullName)},${esc(r2)},${esc(selectors2)},${esc(receiverTypes2)},${esc(receivers2)},${esc(allocCls2)},${esc(mname2)},${esc(ownerMethod2)},${esc(ownerMethodFullName2)},${esc(af)},$al,$ac,${esc(codeStr(cc2))},${isThis2},${esc(segLabels2)},${esc("Call")}")

          case other =>
            val ocode = codeStr(other.asInstanceOf[AnyRef])
            val vid = uid("Var", af, al, ac, s"expr|${ocode}|${m.fullName}")
            val vset = scala.collection.mutable.Set("Var","Expr","CallArg")
            if (assignLeftIds.contains(vid)) vset += "AssignLeft"
            val vmethod = methodNameOf(m)
            val segLabels = arr(vset.toSeq)
            val assignRight = assignRightByVar.getOrElse(vid, "")
            (vid, "Var", mkVarRow(vid, "", "", vmethod, af, al, ac, ocode, segLabels, Nil, Nil, Nil, Nil, "Expr", assignRight, -1))
        }

        kind match {
          case "Var"  => varRows.update(aid, row)
          case "Lit"  => litRows.update(aid, row)
          case "Call" => callRows.update(aid, row)
          case _      => varRows.update(aid, row)
        }

        eArg.add(s"${esc(aid)},${esc(cid)},$argIdx,ARG")

        if (astMode != "none") {
          val astNodes =
            if (astMode == "wide") Try(a.inAstMinusLeaf.l ++ a.ast.l ++ c.ast.l).toOption.getOrElse(Nil)
            else Try(a.ast.l).toOption.getOrElse(Nil)

          astNodes.foreach {
            case ii: Identifier =>
              val nil = lineNum(ii); val nic = colNum(ii)
              val nid = uid("Var", af, nil, nic, s"id|${ii.name}|${m.fullName}")
              val vset = scala.collection.mutable.Set("Var","Identifier","Reference","CallArg")
              if (assignLeftIds.contains(nid)) vset += "AssignLeft"
              val vmethod = methodNameOf(m)
              val segLabels = arr(vset.toSeq)
              val assignRight = assignRightByVar.getOrElse(nid, "")
              varRows.update(nid, mkVarRow(nid, ii.name, typeStr(ii), vmethod, af, nil, nic, codeStr(ii), segLabels, Nil, Nil, Nil, Nil, "Identifier", assignRight, -1))
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case other if isFieldIdentifier(other.asInstanceOf[AnyRef]) =>
              val nil = lineNum(other.asInstanceOf[AnyRef]); val nic = colNum(other.asInstanceOf[AnyRef])
              val name = nameStr(other.asInstanceOf[AnyRef])
              val nid = uid("Var", af, nil, nic, s"field|${name}|${m.fullName}")
              val vset = scala.collection.mutable.Set("Var","FieldIdentifier","Reference","CallArg")
              if (assignLeftIds.contains(nid)) vset += "AssignLeft"
              val vmethod = methodNameOf(m)
              val segLabels = arr(vset.toSeq)
              val assignRight = assignRightByVar.getOrElse(nid, "")
              varRows.update(nid, mkVarRow(nid, name, "", vmethod, af, nil, nic, codeStr(other.asInstanceOf[AnyRef]), segLabels, Nil, Nil, Nil, Nil, "FieldIdentifier", assignRight, -1))
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case ll: Literal =>
              val nll = lineNum(ll); val nlc = colNum(ll)
              val nid = litIdOf(af, nll, nlc, ll.typeFullName, ll.code, m.fullName)
              litRows.update(nid, s"${esc(nid)},${esc("Lit")},${esc(simpleType(ll.typeFullName))},${esc(af)},${nll},${nlc},${esc(ll.code)},${esc("Lit")}")
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case cl2: Call =>
              val ncl = lineNum(cl2); val ncc = colNum(cl2)
              val nid = callIdOf(cl2, af, ncl, ncc)
              val segLabels3 = arr((labelForCall(cl2) + "CallArg").toSeq)
              val r3 = receiverType(cl2)
              val selectors3 = selectorsOf(cl2)
              val receiverTypes3 = receiverTypesOf(cl2)
              val allocCls3 = allocationClassName(cl2)
              val mname3 = Option(cl2.name).getOrElse("")
              val isThis3 = if (isThisReceiver(cl2)) "true" else "false"
              val receivers3 = receiverNamesOf(cl2)
              val ownerMethod3 = methodNameOf(m)
              val ownerMethodFullName3 = methodFullNameOf(m)
              callRows.update(nid, s"${esc(nid)},${esc("Call")},${esc(cl2.name)},${esc(cl2.methodFullName)},${esc(r3)},${esc(selectors3)},${esc(receiverTypes3)},${esc(receivers3)},${esc(allocCls3)},${esc(mname3)},${esc(ownerMethod3)},${esc(ownerMethodFullName3)},${esc(af)},${ncl},${ncc},${esc(codeStr(cl2))},${isThis3},${esc(segLabels3)},${esc("Call")}")
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case _ =>
          }
        }
        }
      }
      }
    }
    }
  }

  // ---------- flush ----------
  nFileD.writeText(fileRows.values.mkString("", "\n", "\n"))
  nMethD.writeText(methRows.values.mkString("", "\n", "\n"))
  nCallD.writeText(callRows.values.mkString("", "\n", "\n"))
  nVarD.writeText(varRows.values.mkString("", "\n", "\n"))
  nLitD.writeText(litRows.values.mkString("", "\n", "\n"))
  nPropD.writeText(propRows.values.mkString("", "\n", "\n"))
  nYmlD.writeText(ymlRows.values.mkString("", "\n", "\n"))
  nPomD.writeText(pomRows.values.mkString("", "\n", "\n"))
  nGradleD.writeText(gradleRows.values.mkString("", "\n", "\n"))
  nXmlD.writeText(xmlRows.values.mkString("", "\n", "\n"))

  eInFileD.writeText(eInFile.mkString("", "\n", "\n"))
  eHasCallD.writeText(eHasCall.mkString("", "\n", "\n"))
  eCallsD.writeText(eCalls.mkString("", "\n", "\n"))
  eArgD.writeText(eArg.mkString("", "\n", "\n"))
  eAstD.writeText(eAst.mkString("", "\n", "\n"))
  eRefD.writeText(eRef.mkString("", "\n", "\n"))

  println(s"[OK] exported to $outDir")
}
