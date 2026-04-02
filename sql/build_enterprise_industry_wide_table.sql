-- odps sql
-- 企业行业识别宽表 V1
-- 目标：
-- 1. 输出主体字段
-- 2. 输出 90 天统计字段
-- 3. 输出近 30 天最新 20 条样本
-- 4. 输出 90 天全量招聘事实，供回放与审计使用

SET odps.stage.joiner.mem=10240;

CREATE TABLE IF NOT EXISTS yuapo_dev.enterprise_industry_wide_table
(
    user_id BIGINT COMMENT '用户ID',
    social_credit_code STRING COMMENT '统一社会信用代码',
    enterprise_name STRING COMMENT '企业名称',
    business_scope STRING COMMENT '经营范围',
    total_job_post_cnt_90d BIGINT COMMENT '近90天招聘总数',
    distinct_job_name_cnt_90d BIGINT COMMENT '近90天去重岗位数',
    top_job_names_json STRING COMMENT '近90天岗位Top10统计JSON',
    jobs_recent_20_json STRING COMMENT '近30天最新20条招聘样本JSON',
    jobs_all_90d_json STRING COMMENT '近90天全量招聘事实JSON'
)
PARTITIONED BY (pt STRING COMMENT '业务日期分区,格式yyyymmdd')
LIFECYCLE 180;

WITH enterprise_master AS (
    SELECT
        user_id,
        social_credit_code,
        name AS enterprise_name,
        business_scope
    FROM (
        SELECT
            user_id,
            social_credit_code,
            name,
            business_scope,
            ROW_NUMBER() OVER (
                PARTITION BY social_credit_code
                ORDER BY updated_at DESC
            ) AS rn
        FROM yuapo.ods_user_central_enterprise_master_data
        WHERE pt = '${bdp.system.bizdate}'
          AND enterprise_status = 2
    ) t
    WHERE rn = 1
),
job_info AS (
    SELECT
        id AS job_id,
        user_id,
        title,
        detail
    FROM yuapo.ods_gczdw_q
    WHERE pt = '${bdp.system.bizdate}'
      AND user_id > 0
      AND is_check = 2
),
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
            ROW_NUMBER() OVER (
                PARTITION BY t3.job_id
                ORDER BY t2.issue_ts DESC
            ) AS rn
        FROM yuapo.enterprise_user_account t1
        JOIN yuapo.dim_info_hist t2
            ON t1.pt = t2.ds
           AND t1.user_id = t2.user_id
           AND t2.info_type = 1
           AND t2.check_status = 1
        JOIN job_info t3
            ON t2.info_id = CAST(t3.job_id AS STRING)
        WHERE t1.pt = '${bdp.system.bizdate}'
          AND FROM_UNIXTIME(t2.issue_ts) >= TO_DATE('${bdp.system.bizdate}', 'yyyymmdd') - 90
          AND FROM_UNIXTIME(t2.issue_ts) < TO_DATE('${bdp.system.bizdate}', 'yyyymmdd') + 1
    ) src
    WHERE rn = 1
      AND title IS NOT NULL
      AND title != ''
),
job_name_stats AS (
    SELECT
        social_credit_code,
        title AS job_name,
        COUNT(1) AS cnt
    FROM job_publish_detail
    GROUP BY social_credit_code, title
),
job_name_ranked AS (
    SELECT
        social_credit_code,
        job_name,
        cnt,
        ROW_NUMBER() OVER (
            PARTITION BY social_credit_code
            ORDER BY cnt DESC, job_name ASC
        ) AS rn,
        SUM(cnt) OVER (PARTITION BY social_credit_code) AS total_cnt
    FROM job_name_stats
),
job_name_top10 AS (
    SELECT
        social_credit_code,
        TO_JSON(
            COLLECT_LIST(
                NAMED_STRUCT(
                    'job_name', job_name,
                    'cnt', cnt,
                    'ratio', IF(total_cnt = 0, 0D, CAST(cnt AS DOUBLE) / CAST(total_cnt AS DOUBLE))
                )
            )
        ) AS top_job_names_json
    FROM job_name_ranked
    WHERE rn <= 10
    GROUP BY social_credit_code
),
job_summary AS (
    SELECT
        social_credit_code,
        COUNT(1) AS total_job_post_cnt_90d,
        COUNT(DISTINCT title) AS distinct_job_name_cnt_90d,
        TO_JSON(
            COLLECT_LIST(
                NAMED_STRUCT(
                    'job_name', title,
                    'desc', detail,
                    'add_time', CAST(add_time AS STRING)
                )
            )
        ) AS jobs_all_90d_json
    FROM job_publish_detail
    GROUP BY social_credit_code
),
recent_jobs_ranked AS (
    SELECT
        social_credit_code,
        title,
        detail,
        add_time,
        ROW_NUMBER() OVER (
            PARTITION BY social_credit_code
            ORDER BY add_time DESC, title ASC
        ) AS rn
    FROM job_publish_detail
    WHERE add_time >= TO_DATE('${bdp.system.bizdate}', 'yyyymmdd') - 30
),
recent_jobs_top20 AS (
    SELECT
        social_credit_code,
        TO_JSON(
            COLLECT_LIST(
                NAMED_STRUCT(
                    'job_name', title,
                    'desc', detail,
                    'add_time', CAST(add_time AS STRING)
                )
            )
        ) AS jobs_recent_20_json
    FROM recent_jobs_ranked
    WHERE rn <= 20
    GROUP BY social_credit_code
)
INSERT OVERWRITE TABLE yuapo_dev.enterprise_industry_wide_table
PARTITION (pt = '${bdp.system.bizdate}')
SELECT
    m.user_id,
    m.social_credit_code,
    m.enterprise_name,
    COALESCE(m.business_scope, '') AS business_scope,
    COALESCE(s.total_job_post_cnt_90d, 0) AS total_job_post_cnt_90d,
    COALESCE(s.distinct_job_name_cnt_90d, 0) AS distinct_job_name_cnt_90d,
    COALESCE(t.top_job_names_json, '[]') AS top_job_names_json,
    COALESCE(r.jobs_recent_20_json, '[]') AS jobs_recent_20_json,
    COALESCE(s.jobs_all_90d_json, '[]') AS jobs_all_90d_json
FROM enterprise_master m
LEFT JOIN job_summary s
    ON m.social_credit_code = s.social_credit_code
LEFT JOIN job_name_top10 t
    ON m.social_credit_code = t.social_credit_code
LEFT JOIN recent_jobs_top20 r
    ON m.social_credit_code = r.social_credit_code
;
