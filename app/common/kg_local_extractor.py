import re


def extract_local_knowledge(batch_text: str, doc_type: str) -> dict:
    """Deterministic fallback extraction for technical Chinese teaching documents."""
    main_text = extract_main_chunk_text(batch_text)
    if not main_text:
        return {"knowledge_points": [], "relations": []}

    sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]+", main_text) if len(s.strip()) >= 8]
    alias_map = _extract_alias_map(main_text)
    entity_evidence = {}

    for zh, alias in alias_map.items():
        if _valid_entity_name(zh):
            entity_evidence.setdefault(zh, f"{zh}（{alias}）")
        if _valid_entity_name(alias):
            entity_evidence.setdefault(alias, f"{zh}（{alias}）")

    for sentence in sentences:
        for name in _extract_definition_heads(sentence):
            entity_evidence.setdefault(name, sentence[:220])
        for name in _extract_technical_terms(sentence):
            entity_evidence.setdefault(name, sentence[:220])

    knowledge_points = []
    for name, evidence in list(entity_evidence.items())[:18]:
        aliases = []
        if name in alias_map:
            aliases.append(alias_map[name])
        aliases.extend([zh for zh, alias in alias_map.items() if alias == name])
        knowledge_points.append({
            "name": name[:100],
            "aliases": sorted({alias for alias in aliases if alias and alias != name})[:5],
            "entity_type": _guess_entity_type(name),
            "description": _make_local_description(name, evidence),
            "difficulty": _guess_difficulty(name, evidence),
            "evidence": evidence[:500],
            "confidence": 0.72,
        })

    names = [kp["name"] for kp in knowledge_points]
    relations = []
    for sentence in sentences:
        present = [name for name in names if name in sentence]
        if len(present) >= 2:
            relations.extend(_infer_sentence_relations(sentence, present, doc_type))

    return {
        "knowledge_points": knowledge_points,
        "relations": _dedup_local_relations(relations)[:24],
    }


def extract_main_chunk_text(batch_text: str) -> str:
    match = re.search(r"\[主切块，实体和证据必须来自这里\]\n(.*?)(?:\n\n---\n\n\[后文|$)", batch_text, re.DOTALL)
    return (match.group(1) if match else batch_text).strip()


def _extract_alias_map(text: str) -> dict:
    alias_map = {}
    patterns = [
        r"([\u4e00-\u9fffA-Za-z0-9·\-]{2,30})[（(]([A-Za-z][A-Za-z0-9_\- ]{1,40})[）)]",
        r"([A-Za-z][A-Za-z0-9_\- ]{1,40})[（(]([\u4e00-\u9fffA-Za-z0-9·\-]{2,30})[）)]",
    ]
    for pattern in patterns:
        for left, right in re.findall(pattern, text):
            left = left.strip()
            right = right.strip()
            if _valid_entity_name(left) and _valid_entity_name(right):
                if re.search(r"[\u4e00-\u9fff]", left):
                    alias_map[left] = right
                else:
                    alias_map[right] = left
    return alias_map


def _extract_definition_heads(sentence: str) -> list:
    heads = []
    definition_patterns = [
        r"([\u4e00-\u9fffA-Za-z0-9·\-]{2,30})(?:是|指|表示|定义为|称为|又称|是一种|是一类)",
        r"(?:所谓|其中|例如|如)([\u4e00-\u9fffA-Za-z0-9·\-]{2,30})(?:是|指|表示|用于)",
    ]
    for pattern in definition_patterns:
        for match in re.findall(pattern, sentence):
            candidate = _clean_entity_name(match)
            if _valid_entity_name(candidate):
                heads.append(candidate)
    return heads


def _extract_technical_terms(sentence: str) -> list:
    terms = set()
    suffixes = (
        "算法", "模型", "网络", "函数", "梯度", "损失", "优化器", "优化算法", "层",
        "机制", "编码器", "解码器", "注意力", "卷积", "池化", "归一化", "正则化",
        "分类器", "表示", "特征", "参数", "矩阵", "向量", "分布", "概率", "回归",
        "分类", "聚类", "训练", "推理", "评估", "误差", "激活函数",
    )
    suffix_pattern = "|".join(re.escape(item) for item in suffixes)
    for match in re.findall(rf"[\u4e00-\u9fffA-Za-z0-9·\-]{{1,22}}(?:{suffix_pattern})", sentence):
        candidate = _clean_entity_name(match)
        if _valid_entity_name(candidate):
            terms.add(candidate)
    for match in re.findall(r"\b(?:CNN|RNN|LSTM|GRU|MLP|BERT|Transformer|ResNet|VGG|GAN|SVM|PCA|SGD|Adam|ReLU|Softmax|Dropout|BatchNorm|LayerNorm)\b", sentence, re.IGNORECASE):
        candidate = match.strip()
        if _valid_entity_name(candidate):
            terms.add(candidate)
    return list(terms)


def _clean_entity_name(name: str) -> str:
    name = re.sub(r"^[的和与及在对将把由为是可需]+", "", (name or "").strip())
    name = re.sub(r"[，,：:；;。.!！?？、].*$", "", name)
    return name.strip(" \t\r\n-—()（）[]【】")


def _valid_entity_name(name: str) -> bool:
    if not name:
        return False
    name = name.strip()
    if len(name) < 2 or len(name) > 40:
        return False
    if name in {"本章", "本文", "我们", "可以", "因此", "由于", "对于", "这个", "这些", "一种", "方法", "问题", "系统", "内容", "数据", "结果", "过程", "方面", "部分"}:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)*", name):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", name))


def _guess_entity_type(name: str) -> str:
    if any(key in name for key in ("算法", "SGD", "Adam", "梯度下降")):
        return "算法"
    if any(key in name for key in ("模型", "网络", "Transformer", "CNN", "RNN", "BERT")):
        return "模型"
    if any(key in name for key in ("函数", "损失", "ReLU", "Softmax")):
        return "函数"
    if any(key in name for key in ("层", "编码器", "解码器", "注意力")):
        return "组件"
    return "概念"


def _guess_difficulty(name: str, evidence: str) -> int:
    if any(key in name + evidence for key in ("Transformer", "注意力", "反向传播", "正则化", "优化器")):
        return 4
    if any(key in name + evidence for key in ("梯度", "损失", "神经网络", "卷积")):
        return 3
    return 2


def _make_local_description(name: str, evidence: str) -> str:
    evidence = re.sub(r"\s+", " ", evidence or "").strip()
    if len(evidence) <= 80:
        return evidence or name
    return f"{name}：{evidence[:76]}..."


def _infer_sentence_relations(sentence: str, present: list, doc_type: str) -> list:
    relations = []
    ordered = sorted(present, key=lambda name: sentence.find(name))
    source = ordered[0]
    for target in ordered[1:4]:
        if source == target:
            continue
        rel_type = "RELATED"
        description = f"{source}与{target}在同一语义片段中关联"
        if re.search(r"包含|包括|由.*组成|分为|组成", sentence):
            rel_type = "CONTAINS"
            description = f"{source}包含或涉及{target}"
        elif re.search(r"基于|依赖|前提|基础|需要|通过.*学习", sentence):
            rel_type = "PREREQUISITE"
            description = f"{source}是理解{target}的相关基础"
        elif re.search(r"然后|接着|之后|下一步|输出到|传递到", sentence):
            rel_type = "NEXT"
            description = f"{target}是{source}的后续过程或扩展"
        elif re.search(r"相比|不同|区别|而|但是|对比|相反", sentence):
            rel_type = "CONTRAST"
            description = f"{source}与{target}存在对比关系"
        elif doc_type == "exam" and re.search(r"考查|题目|选择题|填空题|简答题", sentence):
            rel_type = "EXAMINED_IN"
            description = f"{source}在题目语境中考查{target}"
        relations.append({
            "source": source,
            "target": target,
            "type": rel_type,
            "description": description,
            "evidence": sentence[:500],
            "confidence": 0.82 if rel_type != "RELATED" else 0.68,
        })
    return relations


def _dedup_local_relations(relations: list) -> list:
    seen = set()
    unique = []
    for rel in relations:
        key = (rel.get("source"), rel.get("target"), rel.get("type"))
        if key not in seen:
            seen.add(key)
            unique.append(rel)
    return unique
