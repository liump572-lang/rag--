SET NAMES utf8mb4;

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS knowledge_qa_system
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE knowledge_qa_system;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    total_questions INT DEFAULT 0 COMMENT '总问答数',
    wrong_question_count INT DEFAULT 0 COMMENT '错题数',
    last_login_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 科目表
CREATE TABLE IF NOT EXISTS subjects (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT '科目名称',
    description VARCHAR(255) COMMENT '科目描述',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序号',
    is_built_in TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否内置',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科目表';

-- 插入内置科目
INSERT IGNORE INTO subjects (name, description, sort_order, is_built_in) VALUES
    ('计算机网络', '计算机网络原理与技术', 1, 1),
    ('操作系统', '计算机操作系统原理', 2, 1),
    ('数据库', '数据库系统概论', 3, 1),
    ('计算机组成原理', '计算机组成与结构', 4, 1),
    ('机器学习', '机器学习理论与算法', 5, 1),
    ('深度学习', '深度学习理论与框架', 6, 1),
    ('人工智能', '人工智能导论', 7, 1);

-- 文档表
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    subject_id BIGINT NOT NULL COMMENT '所属科目ID',
    title VARCHAR(255) NOT NULL COMMENT '文档标题',
    file_path VARCHAR(500) NOT NULL COMMENT '文件存储路径',
    file_size BIGINT COMMENT '文件大小(字节)',
    file_type ENUM('pdf', 'docx', 'pptx', 'txt', 'md') NOT NULL COMMENT '文件格式',
    doc_type ENUM('textbook', 'exam', 'note', 'supplement') NOT NULL COMMENT '文档类型',
    parse_status ENUM('pending', 'parsing', 'success', 'failed') DEFAULT 'pending' COMMENT '解析状态',
    error_msg TEXT COMMENT '解析失败原因',
    chunk_count INT DEFAULT 0 COMMENT '分片数',
    parse_revision INT NOT NULL DEFAULT 0 COMMENT '解析版本号',
    year INT COMMENT '真题年份',
    question_type VARCHAR(50) COMMENT '真题题型',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_subject_id (subject_id),
    INDEX idx_doc_type (doc_type),
    INDEX idx_parse_status (parse_status),
    INDEX idx_year (year),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表';

-- 文档片段表
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL COMMENT '所属文档ID',
    chunk_index INT NOT NULL DEFAULT 0 COMMENT '分片序号',
    content MEDIUMTEXT NOT NULL COMMENT '片段内容',
    char_count INT DEFAULT 0 COMMENT '字符数',
    chroma_id VARCHAR(255) COMMENT 'ChromaDB向量ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_document_id (document_id),
    INDEX idx_doc_index (document_id, chunk_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档片段表';

-- 真题试卷表
CREATE TABLE IF NOT EXISTS exam_papers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT COMMENT '关联文档ID',
    subject_id BIGINT NOT NULL COMMENT '科目ID',
    year INT NOT NULL COMMENT '考试年份',
    title VARCHAR(255) COMMENT '试卷标题',
    question_count INT DEFAULT 0 COMMENT '题目数量',
    source ENUM('uploaded', 'api') NOT NULL DEFAULT 'uploaded' COMMENT '来源',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_subject_year (subject_id, year),
    INDEX idx_document_id (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='真题试卷表';

-- 真题题目表
CREATE TABLE IF NOT EXISTS exam_questions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    exam_paper_id BIGINT NOT NULL COMMENT '所属试卷ID',
    question_type ENUM('choice', 'fill', 'short_answer', 'calculation', 'comprehensive') NOT NULL COMMENT '题型',
    content TEXT NOT NULL COMMENT '题目内容',
    options JSON COMMENT '选择题选项',
    answer TEXT COMMENT '答案',
    analysis TEXT COMMENT '解析',
    knowledge_points JSON COMMENT '知识点标签',
    difficulty TINYINT DEFAULT 3 COMMENT '难度等级1-5',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '题号顺序',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_paper_id (exam_paper_id),
    INDEX idx_question_type (question_type),
    INDEX idx_difficulty (difficulty)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='真题题目表';

-- 对话表
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    subject_id BIGINT COMMENT '关联科目ID',
    title VARCHAR(255) COMMENT '对话标题',
    message_count INT DEFAULT 0 COMMENT '消息总数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话表';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT NOT NULL COMMENT '对话ID',
    role ENUM('user', 'assistant', 'system') NOT NULL COMMENT '消息角色',
    content MEDIUMTEXT NOT NULL COMMENT '消息内容',
    sources JSON COMMENT '引用来源',
    question_type ENUM('knowledge', 'exam', 'note') COMMENT '问题类型',
    intent_confidence DECIMAL(4,3) COMMENT '意图置信度',
    feedback_score TINYINT COMMENT '反馈评分(1点赞/-1点踩)',
    token_count INT DEFAULT 0 COMMENT 'Token消耗数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at),
    INDEX idx_question_type (question_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息表';

-- 错题本表
CREATE TABLE IF NOT EXISTS wrong_questions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '学生ID',
    exam_question_id BIGINT COMMENT '关联真题ID',
    message_id BIGINT COMMENT '关联消息ID',
    subject_id BIGINT NOT NULL COMMENT '科目ID',
    question_content TEXT NOT NULL COMMENT '题目内容',
    correct_answer TEXT COMMENT '正确答案',
    user_answer TEXT COMMENT '用户答案',
    error_reason ENUM('knowledge_gap', 'misunderstanding', 'careless', 'other') COMMENT '错误原因',
    difficulty TINYINT DEFAULT 3 COMMENT '难度等级1-5',
    mastery_status ENUM('pending', 'unmastered', 'mastered') NOT NULL DEFAULT 'pending' COMMENT '掌握状态',
    review_count INT DEFAULT 0 COMMENT '复习次数',
    mastered_at DATETIME COMMENT '掌握时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_subject_id (subject_id),
    INDEX idx_mastery_status (mastery_status),
    INDEX idx_difficulty (difficulty),
    INDEX idx_user_subject (user_id, subject_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='错题本表';

-- 学习心得表
CREATE TABLE IF NOT EXISTS study_notes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '作者ID',
    subject_id BIGINT NOT NULL COMMENT '科目ID',
    title VARCHAR(255) NOT NULL COMMENT '标题',
    content MEDIUMTEXT NOT NULL COMMENT '正文(Markdown)',
    tags JSON COMMENT '知识点标签',
    status ENUM('pending', 'published', 'rejected', 'unpublished') NOT NULL DEFAULT 'pending' COMMENT '审核状态',
    reject_reason VARCHAR(255) COMMENT '驳回原因',
    is_pinned TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否置顶',
    like_count INT NOT NULL DEFAULT 0 COMMENT '点赞数',
    favorite_count INT NOT NULL DEFAULT 0 COMMENT '收藏数',
    comment_count INT NOT NULL DEFAULT 0 COMMENT '评论数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_subject_id (subject_id),
    INDEX idx_status (status),
    INDEX idx_pinned_created (is_pinned, created_at),
    INDEX idx_like_count (like_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习心得表';

-- 心得评论表
CREATE TABLE IF NOT EXISTS note_comments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    note_id BIGINT NOT NULL COMMENT '心得ID',
    user_id BIGINT NOT NULL COMMENT '评论者ID',
    content TEXT NOT NULL COMMENT '评论内容',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_note_id (note_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心得评论表';

-- 心得收藏表
CREATE TABLE IF NOT EXISTS note_favorites (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    note_id BIGINT NOT NULL COMMENT '心得ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_note_fav (note_id, user_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心得收藏表';

-- 心得点赞表
CREATE TABLE IF NOT EXISTS note_likes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    note_id BIGINT NOT NULL COMMENT '心得ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_note_like (note_id, user_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心得点赞表';

-- 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE COMMENT '配置键名',
    config_value TEXT NOT NULL COMMENT '配置值',
    description VARCHAR(255) COMMENT '配置说明',
    updated_by BIGINT COMMENT '更新人ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置表';

-- 插入默认配置（config_key 需与后端 system/router.py 和 qa/service.py 中的键名一致）
INSERT IGNORE INTO system_configs (config_key, config_value, description) VALUES
    ('deepseek_api_key', '', '大模型API Key'),
    ('deepseek_api_base', 'https://api.deepseek.com/v1', '大模型API地址'),
    ('llm_model', 'deepseek-v4-flash', '对话模型名称'),
    ('embedding_model', 'deepseek-embedding', 'Embedding模型名称'),
    ('llm.temperature', '0.7', '生成温度'),
    ('llm.max_tokens', '4096', '最大Token数'),
    ('retrieval.top_k', '10', '检索Top-K数量'),
    ('retrieval.similarity_threshold', '0.75', '相似度阈值'),
    ('chunk.size', '512', '文档分块大小'),
    ('chunk.overlap', '128', '分块重叠量'),
    ('chunk.min_chars', '120', '文档最小切块大小'),
    ('kg.relation_candidate_threshold', '0.2', '关系候选保留阈值'),
    ('kg.relation_auto_threshold', '0.8', '关系自动入图阈值'),
    ('kg.batch_chunks', '20', '每个并行抽取分段包含的切块数'),
    ('kg.max_parallel_batches', '8', '图谱抽取最大并行分段数'),
    ('kg.max_active_batches_per_document', '2', '单文档同时抽取的最大分段数'),
    ('kg.batch_retry_limit', '2', '图谱抽取分段失败重试次数'),
    ('kg.cross_relation_top_k', '30', '跨文档关系候选召回数量');

-- 消息通知表
CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '接收用户ID',
    type ENUM('note_approved', 'note_rejected', 'system') NOT NULL DEFAULT 'system' COMMENT '通知类型',
    title VARCHAR(255) NOT NULL COMMENT '通知标题',
    content TEXT COMMENT '通知内容',
    related_id BIGINT COMMENT '关联业务ID',
    is_read TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已读',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notif_user (user_id, is_read, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息通知表';

-- 系统日志表
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT COMMENT '操作用户ID',
    action VARCHAR(100) NOT NULL COMMENT '操作类型',
    module VARCHAR(50) NOT NULL COMMENT '所属模块',
    level ENUM('INFO', 'WARN', 'ERROR') NOT NULL DEFAULT 'INFO' COMMENT '日志级别',
    message TEXT NOT NULL COMMENT '日志内容',
    detail JSON COMMENT '详细信息',
    ip_address VARCHAR(45) COMMENT '请求IP',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_module (module),
    INDEX idx_level (level),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统日志表';

-- 知识点表
CREATE TABLE IF NOT EXISTS knowledge_points (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '知识点名称',
    subject_id BIGINT NOT NULL COMMENT '所属科目ID',
    description TEXT COMMENT '知识点描述',
    difficulty TINYINT DEFAULT 3 COMMENT '难度等级1-5',
    outline_path VARCHAR(255) COMMENT '大纲章节路径',
    neo4j_node_id VARCHAR(255) COMMENT 'Neo4j节点ID',
    origin ENUM('legacy', 'manual', 'auto') NOT NULL DEFAULT 'legacy' COMMENT '数据来源',
    confidence DECIMAL(4,3) NOT NULL DEFAULT 1.000 COMMENT '抽取置信度',
    review_status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending' COMMENT '审核状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_subject_id (subject_id),
    INDEX idx_difficulty (difficulty)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识点表';

-- 知识点关系表
CREATE TABLE IF NOT EXISTS knowledge_relations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_node_id BIGINT NOT NULL COMMENT '源知识点ID',
    target_node_id BIGINT NOT NULL COMMENT '目标知识点ID',
    relation_type ENUM('PREREQUISITE', 'NEXT', 'RELATED', 'CONTAINS', 'CONTRAST', 'EXAMINED_IN') NOT NULL COMMENT '关系类型',
    description VARCHAR(255) COMMENT '关系描述',
    neo4j_rel_id VARCHAR(255) COMMENT 'Neo4j关系ID',
    origin ENUM('legacy', 'manual', 'auto') NOT NULL DEFAULT 'legacy' COMMENT '数据来源',
    confidence DECIMAL(4,3) NOT NULL DEFAULT 1.000 COMMENT '抽取置信度',
    review_status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending' COMMENT '审核状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_relation (source_node_id, target_node_id, relation_type),
    INDEX idx_source (source_node_id),
    INDEX idx_target (target_node_id),
    INDEX idx_relation_type (relation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识点关系表';

CREATE TABLE IF NOT EXISTS knowledge_point_sources (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    knowledge_point_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    chunk_id BIGINT,
    raw_name VARCHAR(100) NOT NULL,
    canonical_name VARCHAR(100) NOT NULL,
    evidence_text TEXT,
    extraction_batch VARCHAR(100),
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.800,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kps_point (knowledge_point_id),
    INDEX idx_kps_document (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识点来源证据';

CREATE TABLE IF NOT EXISTS knowledge_relation_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    relation_id BIGINT,
    document_id BIGINT NOT NULL,
    chunk_id BIGINT,
    source_name VARCHAR(100) NOT NULL,
    target_name VARCHAR(100) NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    evidence_text TEXT,
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.800,
    prompt_version VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kre_relation (relation_id),
    INDEX idx_kre_document (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识点关系证据';

CREATE TABLE IF NOT EXISTS knowledge_relation_candidates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_node_id BIGINT NOT NULL,
    target_node_id BIGINT NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    description VARCHAR(255),
    evidence_text TEXT,
    confidence DECIMAL(4,3) NOT NULL DEFAULT 0.500,
    document_id BIGINT,
    chunk_id BIGINT,
    prompt_version VARCHAR(50) NOT NULL,
    status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    reviewed_by BIGINT,
    reviewed_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_krc_status (status),
    INDEX idx_krc_nodes (source_node_id, target_node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='候选知识点关系';

CREATE TABLE IF NOT EXISTS kg_rebuilds (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    status ENUM('queued', 'running', 'success', 'partial_failed', 'failed') NOT NULL DEFAULT 'queued',
    total_documents INT NOT NULL DEFAULT 0,
    completed_documents INT NOT NULL DEFAULT 0,
    failed_documents INT NOT NULL DEFAULT 0,
    error_msg TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱重建任务';

CREATE TABLE IF NOT EXISTS kg_extraction_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rebuild_id BIGINT,
    document_id BIGINT NOT NULL,
    version VARCHAR(50) NOT NULL,
    status ENUM('queued', 'running', 'success', 'failed', 'canceled') NOT NULL DEFAULT 'queued',
    model VARCHAR(100),
    batch_count INT NOT NULL DEFAULT 0,
    processed_batches INT NOT NULL DEFAULT 0,
    entity_count INT NOT NULL DEFAULT 0,
    relation_count INT NOT NULL DEFAULT 0,
    error_msg TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kger_rebuild (rebuild_id),
    INDEX idx_kger_document (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱文档抽取运行记录';

CREATE TABLE IF NOT EXISTS kg_extraction_batches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    parse_revision INT NOT NULL DEFAULT 0,
    start_index INT NOT NULL,
    end_index INT NOT NULL,
    status ENUM('queued', 'dispatched', 'running', 'success', 'failed', 'stale', 'canceled') NOT NULL DEFAULT 'queued',
    retry_count INT NOT NULL DEFAULT 0,
    entity_count INT NOT NULL DEFAULT 0,
    relation_count INT NOT NULL DEFAULT 0,
    result_json JSON,
    error_msg TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kgeb_run (run_id),
    INDEX idx_kgeb_document (document_id),
    INDEX idx_kgeb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱并行抽取分段';

CREATE TABLE IF NOT EXISTS kg_sync_failures (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_id BIGINT,
    payload JSON,
    error_msg TEXT,
    status ENUM('pending', 'resolved') NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kgsf_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Neo4j同步补偿队列';

-- 第三方题库配置表
CREATE TABLE IF NOT EXISTS third_party_apis (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '题库名称',
    api_url VARCHAR(500) NOT NULL COMMENT 'API地址',
    api_token VARCHAR(500) COMMENT '认证Token',
    sync_interval INT DEFAULT 3600 COMMENT '同步间隔(秒)',
    is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    last_sync_at DATETIME COMMENT '最后同步时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_tp_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='第三方题库配置表';
