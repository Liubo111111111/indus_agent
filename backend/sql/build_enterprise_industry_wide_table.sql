-- odps sql
-- 企业行业识别宽表 V1
-- 目标：
-- 1. 输出主体字段
-- 2. 输出 90 天统计字段
-- 3. 输出近 30 天最新 20 条样本
-- 4. (已移除) 90 天全量招聘事实

SET odps.stage.joiner.mem=10240;

DROP TABLE IF EXISTS yuapo_dev.enterprise_industry_wide_table;

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
    latest_publish_time STRING COMMENT '最新一次发布时间',
    latest_publish_job_names_json STRING COMMENT '最新一次发布的工种JSON',
    authentication_time STRING COMMENT '企业认证时间'
)
PARTITIONED BY (pt STRING COMMENT '业务日期分区,格式yyyymmdd')
LIFECYCLE 180;

WITH enterprise_master AS (
    SELECT
        user_id,
        social_credit_code,
        name AS enterprise_name,
        business_scope,
        SUBSTR(CAST(authentication_time AS STRING), 1, 10) AS authentication_time
    FROM (
        SELECT
            user_id,
            social_credit_code,
            name,
            business_scope,
            authentication_time,
            ROW_NUMBER() OVER (
                PARTITION BY social_credit_code
                ORDER BY updated_at DESC
            ) AS rn
        FROM yuapo.ods_user_central_enterprise_master_data
        WHERE pt = '20210807'
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
    WHERE pt = '20210807'
      AND user_id > 0
      AND is_check = 2
),
job_publish_detail AS (
    SELECT
        social_credit_code,
        prim_gz_names,
        detail,
        add_time
    FROM (
        SELECT
            t1.social_credit_code,
            t2.prim_gz_names,
            t3.detail,
            FROM_UNIXTIME(t2.issue_ts) AS add_time,
            ROW_NUMBER() OVER (
                PARTITION BY t3.job_id
                ORDER BY t2.issue_ts DESC
            ) AS rn
        FROM enterprise_master t1
        JOIN yuapo.dim_info_hist t2
            ON t2.ds = '${bdp.system.bizdate}'
           AND t1.user_id = t2.user_id
           AND t2.info_type = 1
           AND t2.check_status = 1
        JOIN job_info t3
            ON t2.info_id = CAST(t3.job_id AS STRING)
        WHERE FROM_UNIXTIME(t2.issue_ts) >= DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -90, 'dd')
          AND FROM_UNIXTIME(t2.issue_ts) < DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), 1, 'dd')
    ) src
    WHERE rn = 1
      AND prim_gz_names IS NOT NULL
      AND SIZE(prim_gz_names) > 0
),
-- 将 prim_gz_names（ARRAY<STRING>）拆分为独立行
-- 例如 ["家电维修/清洗/安装", "小工/拆除/打磨/打孔"] → 两行
job_publish_exploded AS (
    SELECT
        social_credit_code,
        TRIM(gz_name) AS title,
        detail,
        add_time
    FROM job_publish_detail
    LATERAL VIEW EXPLODE(prim_gz_names) tmp AS gz_name
    WHERE TRIM(gz_name) IS NOT NULL
      AND TRIM(gz_name) != ''
),
job_name_stats AS (
    SELECT
        social_credit_code,
        title AS job_name,
        COUNT(1) AS cnt
    FROM job_publish_exploded
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
                    'ratio', IF(total_cnt = 0, 0D, ROUND(CAST(cnt AS DOUBLE) / CAST(total_cnt AS DOUBLE), 2))
                )
            )
        ) AS top_job_names_json
    FROM job_name_ranked
    WHERE rn <= 10
    GROUP BY social_credit_code
),
job_summary_agg AS (
    SELECT
        social_credit_code,
        COUNT(1) AS total_job_post_cnt_90d,
        COUNT(DISTINCT title) AS distinct_job_name_cnt_90d
    FROM job_publish_exploded
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
    FROM job_publish_exploded
    WHERE add_time >= DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -30, 'dd')
),
recent_jobs_top20 AS (
    SELECT
        social_credit_code,
        TO_JSON(
            COLLECT_LIST(
                NAMED_STRUCT(
                    'job_name', title,
                    'desc', detail,
                    'add_time', SUBSTR(CAST(add_time AS STRING), 1, 10)
                )
            )
        ) AS jobs_recent_20_json
    FROM recent_jobs_ranked
    WHERE rn <= 20
    GROUP BY social_credit_code
),
-- 最新一次发布：取每个企业最近一条发布记录的时间和工种
latest_publish_ranked AS (
    SELECT
        social_credit_code,
        title,
        add_time,
        ROW_NUMBER() OVER (
            PARTITION BY social_credit_code
            ORDER BY add_time DESC, title ASC
        ) AS rn
    FROM job_publish_exploded
),
latest_publish AS (
    SELECT
        lp.social_credit_code,
        SUBSTR(CAST(lp.add_time AS STRING), 1, 10) AS latest_publish_time,
        TO_JSON(
            COLLECT_LIST(lp2.title)
        ) AS latest_publish_job_names_json
    FROM latest_publish_ranked lp
    JOIN (
        -- 取与最新发布时间相同的所有工种
        SELECT
            a.social_credit_code,
            a.title
        FROM job_publish_exploded a
        JOIN (
            SELECT social_credit_code, add_time
            FROM latest_publish_ranked
            WHERE rn = 1
        ) b
            ON a.social_credit_code = b.social_credit_code
           AND a.add_time = b.add_time
        GROUP BY a.social_credit_code, a.title
    ) lp2
        ON lp.social_credit_code = lp2.social_credit_code
    WHERE lp.rn = 1
    GROUP BY lp.social_credit_code, lp.add_time
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
    lp.latest_publish_time,
    COALESCE(lp.latest_publish_job_names_json, '[]') AS latest_publish_job_names_json,
    m.authentication_time
FROM enterprise_master m
INNER JOIN job_summary_agg s
    ON m.social_credit_code = s.social_credit_code
LEFT JOIN job_name_top10 t
    ON m.social_credit_code = t.social_credit_code
LEFT JOIN recent_jobs_top20 r
    ON m.social_credit_code = r.social_credit_code
LEFT JOIN latest_publish lp
    ON m.social_credit_code = lp.social_credit_code
;
