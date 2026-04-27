-- 新旧标签对比评估：宽表 JOIN 老标签表
-- 用途：从 ODPS 拉取企业宽表数据并关联老标签，供 ComparisonEngine 重跑 LLM 分类流水线
--
-- 占位符说明（通过 sql_template.py 的 render_sql 函数渲染）：
--   ${bizdate}       — 宽表及老标签表分区日期（yyyymmdd）
--   ${publish_start} — 发布时间范围起始（yyyy-mm-dd），含当天
--   ${publish_end}   — 发布时间范围结束（yyyy-mm-dd），不含当天

SELECT w.user_id, w.social_credit_code, w.enterprise_name, w.business_scope,
       w.total_job_post_cnt_90d, w.distinct_job_name_cnt_90d, w.top_job_names_json,
       w.jobs_recent_20_json, w.latest_publish_time, w.latest_publish_job_names_json,
       w.authentication_time,
       l.label as old_label
FROM yuapo_dev.enterprise_industry_wide_table w
INNER JOIN yuapo_dev.indus_enterprise_goss_label l
  ON w.user_id = l.user_id
  AND w.social_credit_code = l.social_credit_code
  AND l.pt = '${bizdate}'
WHERE w.pt = '${bizdate}'
  AND w.latest_publish_time >= '${publish_start}'
  AND w.latest_publish_time < '${publish_end}'
