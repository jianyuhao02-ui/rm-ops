"""测试服务器启动脚本"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SAMSUNG_PORT'] = '9528'
os.environ['SAMSUNG_SCHEDULER_ENABLED'] = 'false'

import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=9528, log_level='error')
