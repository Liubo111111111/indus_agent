"""
数据获取模块 - 定时从ODPS获取数据并保存为CSV
"""
from odps import ODPS
import csv
import pandas as pd
from datetime import datetime, timedelta
import os
import logging
from logging.handlers import RotatingFileHandler
import time
import socket
from urllib3.exceptions import MaxRetryError, NewConnectionError
from requests.exceptions import ConnectionError

# 导入配置管理
from settings import get_settings, get_config_manager, ConfigurationError


# 配置日志
def setup_logger():
    """配置日志记录器（使用配置文件中的设置）"""
    try:
        config_manager = get_config_manager()
        config_manager.load_config()
        settings = get_settings()
        log_config = settings.log
        log_dir = config_manager.resolve_path(settings.data.logs_dir)
    except Exception:
        # 如果配置加载失败，使用默认值
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        log_config = None
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'data_fetcher.log')
    
    # 创建logger
    logger = logging.getLogger('data_fetcher')
    log_level = getattr(logging, log_config.level if log_config else 'INFO', logging.INFO)
    logger.setLevel(log_level)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 文件handler（带轮转）
    max_bytes = log_config.max_bytes if log_config else 10*1024*1024
    backup_count = log_config.backup_count if log_config else 5
    log_format = log_config.format if log_config else '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = log_config.date_format if log_config else '%Y-%m-%d %H:%M:%S'
    
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    
    # 控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt=date_format
    )
    console_handler.setFormatter(console_formatter)
    
    # 添加handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 初始化logger
logger = setup_logger()


class OdpsSDK():
    """ODPS SDK 封装类（使用配置文件中的连接参数）"""
    
    def __init__(self, max_retries=3, retry_delay=5):
        """
        初始化 ODPS SDK
        :param max_retries: 最大重试次数
        :param retry_delay: 重试延迟（秒）
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 从配置获取 ODPS 连接参数
        try:
            settings = get_settings()
            odps_config = settings.odps
            
            if not odps_config.is_configured():
                raise ConfigurationError(
                    "ODPS 配置不完整，请设置 access_key_id 和 access_key_secret，"
                    "可通过配置文件或环境变量 ODPS_ACCESS_KEY_ID/ODPS_ACCESS_KEY_SECRET 设置"
                )
            
            self.odps = ODPS(
                odps_config.access_key_id,
                odps_config.access_key_secret,
                odps_config.project,
                endpoint=odps_config.endpoint
            )
            self.endpoint = odps_config.endpoint
            logger.info(f"ODPS 连接初始化成功，项目: {odps_config.project}")
        except ConfigurationError:
            raise
        except Exception as e:
            logger.error(f"ODPS 连接初始化失败: {e}")
            raise
    
    def check_network_connectivity(self):
        """
        检查网络连接是否正常
        :return: True 如果网络正常，False 否则
        """
        try:
            # 从 endpoint 提取主机名
            host = self.endpoint.replace('http://', '').replace('https://', '').split('/')[0].split(':')[0]
            logger.debug(f"检查网络连接到: {host}")
            
            # 尝试 DNS 解析
            socket.gethostbyname(host)
            logger.debug(f"DNS 解析成功: {host}")
            return True
        except socket.gaierror as e:
            logger.error(f"DNS 解析失败: {e}")
            return False
        except Exception as e:
            logger.error(f"网络连接检查失败: {e}")
            return False
    
    def excute_odps_sql(self, sql):
        """
        执行 ODPS SQL 查询（带重试机制）
        :param sql: SQL 查询语句
        :return: 查询结果列表
        """
        rv = []
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # 在执行前检查网络连接
                if not self.check_network_connectivity():
                    logger.warning(f"网络连接检查失败，尝试 {attempt + 1}/{self.max_retries}")
                    if attempt < self.max_retries - 1:
                        logger.info(f"等待 {self.retry_delay} 秒后重试...")
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        raise ConnectionError("网络连接失败，无法连接到 ODPS 服务")
                
                logger.debug(f"执行ODPS SQL查询 (尝试 {attempt + 1}/{self.max_retries})")
                with self.odps.execute_sql(sql).open_reader() as reader:
                    for record in reader:
                        _data = {}
                        for i in record._columns:
                            _data[i.name] = record.get_by_name(i.name)
                        rv.append(_data)
                logger.info(f"SQL查询执行成功，返回 {len(rv)} 条记录")
                return rv
                
            except (ConnectionError, MaxRetryError, NewConnectionError, socket.gaierror) as e:
                last_error = e
                logger.warning(f"网络连接错误 (尝试 {attempt + 1}/{self.max_retries}): {type(e).__name__}")
                
                if attempt < self.max_retries - 1:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"达到最大重试次数，执行SQL失败: {e}")
                    
            except Exception as e:
                last_error = e
                logger.error(f"执行SQL出错 (尝试 {attempt + 1}/{self.max_retries}): {e}", exc_info=True)
                
                # 对于非网络错误，不重试
                if "name resolution" not in str(e).lower() and "connection" not in str(e).lower():
                    logger.error("非网络错误，停止重试")
                    break
                
                if attempt < self.max_retries - 1:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
        
        # 所有重试都失败
        if last_error:
            logger.error(f"所有重试均失败，最后错误: {last_error}")
        
        return rv


def get_yesterday_date():
    """获取昨天的日期（T-1）"""
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y%m%d')
    logger.debug(f"获取昨天日期: {date_str}")
    return date_str


def fetch_data(dt=None, output_dir=None, max_retries=3, retry_delay=5):
    """
    从ODPS获取指定日期的数据并保存为CSV
    :param dt: 日期字符串，格式 YYYYMMDD，默认为T-1（昨天）
    :param output_dir: 输出目录（默认使用配置文件中的 data.data_dir）
    :param max_retries: 最大重试次数
    :param retry_delay: 重试延迟（秒）
    :return: CSV文件路径
    """
    if dt is None:
        dt = get_yesterday_date()
    
    if output_dir is None:
        # 从配置获取数据目录
        try:
            config_manager = get_config_manager()
            settings = config_manager.get_settings()
            output_dir = config_manager.resolve_path(settings.data.data_dir)
        except Exception:
            # 配置加载失败时使用默认目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(current_dir, 'data')
    
    max_rows_env = os.getenv("DATA_FETCHER_MAX_ROWS", "").strip()
    max_rows = None
    if max_rows_env:
        try:
            max_rows = int(max_rows_env)
            if max_rows <= 0:
                logger.warning(f"DATA_FETCHER_MAX_ROWS={max_rows_env} 非法，忽略该限制")
                max_rows = None
        except ValueError:
            logger.warning(f"DATA_FETCHER_MAX_ROWS={max_rows_env} 不是整数，忽略该限制")
            max_rows = None

    logger.info("=" * 60)
    logger.info(f"开始获取数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"目标日期: {dt}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"重试配置: 最大重试次数={max_retries}, 重试延迟={retry_delay}秒")
    if max_rows is not None:
        logger.info(f"最大拉取条数限制: {max_rows}")
    logger.info("=" * 60)
    
    # 分批查询配置
    batch_size = 1000
    offset = 0
    total_rows = 0

    try:
        odps_sdk = OdpsSDK(max_retries=max_retries, retry_delay=retry_delay)
    except Exception as e:
        logger.error(f"ODPS SDK 初始化失败: {e}", exc_info=True)
        logger.error("请检查: 1.网络连接 2.DNS解析 3.ODPS配置 4.防火墙/代理")
        return None

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'negtivate_data_{dt}.csv')
    header_written = False

    logger.info(f"开始分批查询，每批 {batch_size} 条")

    while True:
        if max_rows is not None and total_rows >= max_rows:
            logger.info(f"达到最大拉取条数限制 {max_rows}，停止继续查询")
            break

        current_batch_limit = batch_size
        if max_rows is not None:
            remain = max_rows - total_rows
            current_batch_limit = min(batch_size, remain)

        batch_sql = f"""
SELECT
  user_id,
  info_id,
  job_detail,
  occupation_id,
  sub_id,
  asr_result,
  im_text,
  complaint_content,
  pt
FROM yuapo_dev.ads_risk_cengliu
WHERE pt = '{dt}'
ORDER BY user_id
LIMIT {current_batch_limit} OFFSET {offset}
        """

        try:
            logger.info(f"正在查询第 {offset // batch_size + 1} 批 (OFFSET={offset})...")
            data = odps_sdk.excute_odps_sql(batch_sql)
        except Exception as e:
            logger.error(f"第 {offset // batch_size + 1} 批查询失败: {e}", exc_info=True)
            break

        if not data:
            logger.info(f"第 {offset // batch_size + 1} 批无数据，查询结束")
            break

        try:
            df_batch = pd.DataFrame(data)
            # 首批写header，后续追加
            df_batch.to_csv(
                output_path,
                mode='a' if header_written else 'w',
                header=not header_written,
                index=False,
                encoding='utf-8-sig',
                quoting=csv.QUOTE_ALL,
                escapechar='\\'
            )
            header_written = True
            total_rows += len(df_batch)
            logger.info(f"第 {offset // batch_size + 1} 批写入 {len(df_batch)} 条，累计 {total_rows} 条")
        except Exception as e:
            logger.error(f"第 {offset // batch_size + 1} 批数据写入失败: {e}", exc_info=True)
            break

        # 本批不足本次查询 limit，说明已经是最后一批
        if len(data) < current_batch_limit:
            break

        offset += batch_size

    if total_rows == 0:
        logger.warning(f"日期 {dt} 没有获取到任何数据")
        return None

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"全部完成，共 {total_rows} 条记录，文件: {output_path} ({file_size:.2f} MB)")
    logger.info("=" * 60)
    return output_path


def main(dt=None):
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("数据获取任务开始")
        logger.info("=" * 60)
        csv_path = fetch_data(dt)
        if csv_path:
            logger.info("数据获取成功！")
            logger.info(f"CSV文件路径: {csv_path}")
            return csv_path
        else:
            logger.warning("数据获取失败！未获取到数据")
            return None
    except Exception as e:
        logger.error(f"数据获取过程中发生错误: {e}", exc_info=True)
        return None


if __name__ == '__main__':
    import sys
    dt = sys.argv[1] if len(sys.argv) > 1 else None
    logger.info(f"脚本启动，参数: dt={dt}")
    result = main(dt)
    if result:
        logger.info("脚本执行成功")
    else:
        logger.error("脚本执行失败")

