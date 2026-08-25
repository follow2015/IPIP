/**
 * 页面加载骨架屏组件
 */
import { Spin } from 'antd';


function PageLoading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <Spin size="large"><div /></Spin>
    </div>
  );
}

export default PageLoading;
