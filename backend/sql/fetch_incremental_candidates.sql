-- odps sql
-- 增量模式：每天运行一次
-- 从宽表中取昨天新认证且昨天有发布岗位的企业 → 直接调大模型

SELECT
    w.user_id,
    w.social_credit_code,
    w.enterprise_name,
    w.business_scope,
    w.total_job_post_cnt_90d,
    w.distinct_job_name_cnt_90d,
    w.top_job_names_json,
    w.jobs_recent_20_json,
    w.latest_publish_time,
    w.latest_publish_job_names_json,
    w.authentication_time
FROM yuapo_dev.enterprise_industry_wide_table w
WHERE w.pt = '${bdp.system.bizdate}'
  -- 昨天认证的企业
  AND w.authentication_time >= TO_CHAR(
        DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -1, 'dd'),
        'yyyy-mm-dd'
      )
  AND w.authentication_time < TO_CHAR(
        TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'),
        'yyyy-mm-dd'
      )
  -- 且昨天有发布岗位
  AND w.latest_publish_time >= TO_CHAR(
        DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -1, 'dd'),
        'yyyy-mm-dd'
      )
  AND w.latest_publish_time < TO_CHAR(
        TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'),
        'yyyy-mm-dd'
      )
ORDER BY w.user_id
;
