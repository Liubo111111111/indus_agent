-- odps sql
-- 历史模式：每周运行一次
-- 从宽表中取最近 90 天有发布的企业，LEFT JOIN 结果表
-- 只取「最近 7 天有新发布」或「结果表中无记录」的企业 → 需要调大模型
-- 其余企业直接复用结果表中的已有分类结果

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
    w.authentication_time,
    -- 标记：是否需要调用大模型
    CASE
        WHEN r.social_credit_code IS NULL THEN 1              -- 结果表无记录，需要分类
        WHEN w.latest_publish_time >= TO_CHAR(
                DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -7, 'dd'),
                'yyyy-mm-dd'
             ) THEN 1                                          -- 最近 7 天有新发布，需要重新分类
        ELSE 0                                                 -- 数据无变化，跳过
    END AS need_classification
FROM yuapo_dev.enterprise_industry_wide_table w
LEFT JOIN yuapo_dev.enterprise_industry_label r
    ON w.social_credit_code = r.social_credit_code
WHERE w.pt = '${bdp.system.bizdate}'
  -- 宽表本身已经是 90 天有发布的企业（建表时 INNER JOIN job_summary_agg 保证）
  -- 只输出需要调大模型的企业
  AND (
      r.social_credit_code IS NULL                             -- 结果表无记录
      OR w.latest_publish_time >= TO_CHAR(
            DATEADD(TO_DATE('${bdp.system.bizdate}', 'yyyymmdd'), -7, 'dd'),
            'yyyy-mm-dd'
         )                                                     -- 最近 7 天有新发布
  )
ORDER BY w.user_id
;
