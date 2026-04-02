--odps sql
--********************************************************************--
-- author:liubo1
-- create time:2026-04-01 14:24:33
-- update time:2026-04-02
-- description: 企业行业分类特征提取 — 完整版
--
-- 不依赖 enterprise_job_pub_detail 中间表，直接从上游源表拼出：
--   - 企业主体信息（名称 + 经营范围）
--   - 近 3 个月岗位发布明细（title + detail + add_time）
--
-- 上游源表：
--   1. yuapo.ods_user_central_enterprise_master_data  — 企业主体
--   2. yuapo.enterprise_user_account                  — 企业账号关联
--   3. yuapo.dim_info_hist                            — 岗位发布历史
--   4. yuapo.ods_gczdw_q                              — 岗位详情（title/detail）
--
-- 输出表：yuapo_dev.enterprise_industry_feature
-- feature_json 格式：
--   {
--     "name":  "企业名称",
--     "scope": "经营范围",
--     "jobs":  [
--       {"job_name":"岗位1", "desc":"描述1", "add_time":"2026-03-15 09:30:00"},
--       ...
--     ]
--   }
--********************************************************************--

SET odps.stage.joiner.mem=10240;

-- ============================================================
-- 建表（首次执行，已存在可跳过）
-- ============================================================
CREATE TABLE IF NOT EXISTS yuapo_dev.enterprise_industry_feature
(
    user_id                 BIGINT  COMMENT '用户ID'
    ,social_credit_code     STRING  COMMENT '统一社会信用代码'
    ,feature_json           STRING  COMMENT '特征JSON:{name,scope,jobs[]}'
)
COMMENT '企业行业分类特征数据'
PARTITIONED BY (pt STRING COMMENT '业务日期分区,格式yyyymmdd')
LIFECYCLE 180;

-- ============================================================
-- 步骤 1：获取企业主体信息
-- 来源：ods_user_central_enterprise_master_data
-- 逻辑：enterprise_status=2，按 social_credit_code 去重取最新
-- ============================================================
WITH enterprise_master AS (
    SELECT
        user_id,
        social_credit_code,
        name                AS enterprise_name,
        business_scope
    FROM (
        SELECT
            user_id,
            social_credit_code,
            name,
            business_scope,
            ROW_NUMBER() OVER(
                PARTITION BY social_credit_code
                ORDER BY updated_at DESC
            ) AS rn
        FROM yuapo.ods_user_central_enterprise_master_data
        WHERE pt = '20210807'
          AND enterprise_status = 2
    ) t
    WHERE rn = 1
),

-- ============================================================
-- 步骤 2：获取岗位详情（title + detail）
-- 来源：ods_gczdw_q
-- 逻辑：is_check=2 且 user_id>0，取 job_id/user_id/title/detail
-- ============================================================
job_info AS (
    SELECT
        id       AS job_id,
        user_id,
        title,
        detail
    FROM yuapo.ods_gczdw_q
    WHERE pt = '20210807'
      AND user_id > 0
      AND is_check = 2
),

-- ============================================================
-- 步骤 3：从上游源表直接拼出近 3 个月岗位发布明细
-- 来源：enterprise_user_account + dim_info_hist + job_info
-- 逻辑：
--   - 先过滤近 3 个月的发布记录（add_time 范围）
--   - 再按 job_id 去重（同一岗位多次上架只保留最近一条）
--   - add_time = FROM_UNIXTIME(issue_ts)，即岗位实际发布时间
-- ============================================================
job_publish_detail AS (
    SELECT
        social_credit_code,
        title,
        detail,
        add_time
    FROM (
        SELECT
            t1.social_credit_code,
            t3.title,
            t3.detail,
            FROM_UNIXTIME(t2.issue_ts) AS add_time,
            ROW_NUMBER() OVER(
                PARTITION BY t3.job_id
                ORDER BY t2.issue_ts DESC
            ) AS rn
        FROM yuapo.enterprise_user_account  t1
        JOIN yuapo.dim_info_hist            t2
            ON  t1.pt = t2.ds
            AND t1.user_id = t2.user_id
            AND t2.info_type = 1
            AND t2.check_status = 1
        JOIN job_info                       t3
            ON t2.info_id = CAST(t3.job_id AS STRING)
        WHERE t1.pt = '${bdp.system.bizdate}'
          AND FROM_UNIXTIME(t2.issue_ts) >= TO_DATE('${bdp.system.bizdate}', 'yyyymmdd') - 90
          AND FROM_UNIXTIME(t2.issue_ts) <  TO_DATE('${bdp.system.bizdate}', 'yyyymmdd') + 1
    ) sub
    WHERE rn = 1
),

-- ============================================================
-- 步骤 4：按企业聚合岗位，输出 jobs[] 对象数组
-- 不做前置截断，全量保留给画像层聚合
-- ============================================================
enterprise_jobs AS (
    SELECT
        social_credit_code,
        COLLECT_LIST(
            NAMED_STRUCT(
                'job_name', title,
                'desc',     detail,
                'add_time', CAST(add_time AS STRING)
            )
        ) AS jobs
    FROM job_publish_detail
    WHERE title IS NOT NULL
      AND title != ''
    GROUP BY social_credit_code
)

-- ============================================================
-- 步骤 5：拼接主体信息 + 招聘信息，组装 feature_json，写入目标表
-- LEFT JOIN 保证没有招聘记录的企业也会输出（jobs 为空数组）
-- ============================================================
INSERT OVERWRITE TABLE yuapo_dev.enterprise_industry_feature
    PARTITION(pt = '${bdp.system.bizdate}')
SELECT
    m.user_id,
    m.social_credit_code,
    CONCAT(
        '{"name":"',
        COALESCE(
            REPLACE(REPLACE(m.enterprise_name, '\\', '\\\\'), '"', '\\"'),
            ''
        ),
        '","scope":"',
        COALESCE(
            REPLACE(REPLACE(m.business_scope, '\\', '\\\\'), '"', '\\"'),
            ''
        ),
        '","jobs":',  COALESCE(TO_JSON(j.jobs), '[]'),
        '}'
    ) AS feature_json
FROM enterprise_master m
LEFT JOIN enterprise_jobs j
    ON m.social_credit_code = j.social_credit_code
;
