// ng serve --proxy-config: /api -> API_TARGET (por defecto el API de la maqueta en :8010).
module.exports = { '/api': { target: process.env.API_TARGET || 'http://127.0.0.1:8010', secure: false, changeOrigin: true, pathRewrite: { '^/api': '' } } };
