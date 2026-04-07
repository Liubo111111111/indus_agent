--odps sql
--********************************************************************--
-- description: 行业分类测试数据抽样
--   从 enterprise_industry_feature 按工种过滤，每个行业选 2 个代表工种，
--   每个工种随机抽取 10 条，共 10 行业 × 2 工种 × 10 条 = 200 条
--
-- 使用方式：将 ${bizdate} 替换为目标分区日期，如 20260401
--********************************************************************--

-- ============================================================
-- 展开 jobs 数组，每行一个岗位，便于按 job_name 过滤
-- ============================================================
WITH job_exploded AS (
    SELECT
        user_id,
        social_credit_code,
        feature_json,
        job_item['job_name'] AS job_name
    FROM yuapo_dev.enterprise_industry_feature
    LATERAL VIEW EXPLODE(FROM_JSON(GET_JSON_OBJECT(feature_json, '$.job'),
        'array<map<string,string>>')) tmp AS job_item
    WHERE pt = '20260331'
),

-- ============================================================
-- 按工种打标签，每条记录标注所属行业和工种（模糊匹配）
-- ============================================================
labeled AS (
    SELECT
        user_id,
        social_credit_code,
        feature_json,
        job_name,
        CASE
            -- 1. 汽车租赁
            WHEN job_name LIKE '%网约车%' OR job_name LIKE '%货运司机%'   THEN '汽车租赁'
            -- 2. 娱乐服务
            WHEN job_name LIKE '%按摩%'   OR job_name LIKE '%足疗%'       THEN '娱乐服务'
            -- 3. 文化传媒
            WHEN job_name LIKE '%主播%'   OR job_name LIKE '%直播运营%'   THEN '文化传媒'
            -- 4. 家政服务
            WHEN job_name LIKE '%保姆%'   OR job_name LIKE '%月嫂%'       THEN '家政服务'
            -- 5. 物业管理
            WHEN job_name LIKE '%物业管理%' OR job_name LIKE '%保洁%'     THEN '物业管理'
            -- 6. 接单类平台
            WHEN job_name LIKE '%家电维修%' OR job_name LIKE '%家政保洁%' THEN '接单类平台'
            -- 7. 安保服务
            WHEN job_name LIKE '%保安%'   OR job_name LIKE '%押运%'       THEN '安保服务'
            -- 8. 建筑类
            WHEN job_name LIKE '%钢筋%'   OR job_name LIKE '%泥瓦%'       THEN '建筑类'
            -- 9. 骑手配送
            WHEN job_name LIKE '%骑手%'   OR job_name LIKE '%快递%'       THEN '骑手配送'
            -- 10. 餐饮服务
            WHEN job_name LIKE '%厨师%'   OR job_name LIKE '%服务员%'     THEN '餐饮服务'
        END AS industry,
        CASE
            WHEN job_name LIKE '%网约车%'    THEN '网约车'
            WHEN job_name LIKE '%货运司机%'  THEN '货运司机'
            WHEN job_name LIKE '%按摩%'      THEN '按摩'
            WHEN job_name LIKE '%足疗%'      THEN '足疗'
            WHEN job_name LIKE '%主播%'      THEN '主播'
            WHEN job_name LIKE '%直播运营%'  THEN '直播运营'
            WHEN job_name LIKE '%保姆%'      THEN '保姆'
            WHEN job_name LIKE '%月嫂%'      THEN '月嫂'
            WHEN job_name LIKE '%物业管理%'  THEN '物业管理'
            WHEN job_name LIKE '%保洁%'      THEN '保洁'
            WHEN job_name LIKE '%家电维修%'  THEN '家电维修'
            WHEN job_name LIKE '%家政保洁%'  THEN '家政保洁'
            WHEN job_name LIKE '%保安%'      THEN '保安'
            WHEN job_name LIKE '%押运%'      THEN '押运'
            WHEN job_name LIKE '%钢筋%'      THEN '钢筋'
            WHEN job_name LIKE '%泥瓦%'      THEN '泥瓦'
            WHEN job_name LIKE '%骑手%'      THEN '骑手'
            WHEN job_name LIKE '%快递%'      THEN '快递'
            WHEN job_name LIKE '%厨师%'      THEN '厨师'
            WHEN job_name LIKE '%服务员%'    THEN '服务员'
        END AS job_keyword
    FROM job_exploded
    WHERE job_name LIKE '%网约车%'    OR job_name LIKE '%货运司机%'
       OR job_name LIKE '%按摩%'      OR job_name LIKE '%足疗%'
       OR job_name LIKE '%主播%'      OR job_name LIKE '%直播运营%'
       OR job_name LIKE '%保姆%'      OR job_name LIKE '%月嫂%'
       OR job_name LIKE '%物业管理%'  OR job_name LIKE '%保洁%'
       OR job_name LIKE '%家电维修%'  OR job_name LIKE '%家政保洁%'
       OR job_name LIKE '%保安%'      OR job_name LIKE '%押运%'
       OR job_name LIKE '%钢筋%'      OR job_name LIKE '%泥瓦%'
       OR job_name LIKE '%骑手%'      OR job_name LIKE '%快递%'
       OR job_name LIKE '%厨师%'      OR job_name LIKE '%服务员%'
),

-- ============================================================
-- 每个工种内随机排序，取前 10 条
-- ============================================================
ranked AS (
    SELECT
        industry,
        job_keyword,
        job_name,
        user_id,
        social_credit_code,
        feature_json,
        ROW_NUMBER() OVER(
            PARTITION BY job_keyword
            ORDER BY RAND()
        ) AS rn
    FROM labeled
    WHERE industry IS NOT NULL
)

-- ============================================================
-- 输出最终结果，按行业 + 工种排序便于查看
-- ============================================================
SELECT
    industry,
    job_keyword,
    job_name,
    user_id,
    social_credit_code,
    feature_json
FROM ranked
WHERE rn <= 10
;

-- SELECT
-- user_id,
-- social_credit_code,
-- feature_json,
-- pt
-- FROM yuapo_dev.enterprise_industry_feature
-- WHERE pt = '20260331'
-- LIMIT 10