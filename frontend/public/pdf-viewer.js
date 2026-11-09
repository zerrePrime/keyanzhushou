/**
 * PDF Viewer —— 纯原生 JS，不经过 Vite 编译
 * 暴露 window.PDFViewer 全局对象供 Vue 组件调用
 */
(function () {
  'use strict';

  const pdfjsLib = window.pdfjsLib;
  pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js';

  let currentDoc = null;
  let currentPageNum = 1;
  let currentScale = 1.2;
  let totalPages = 0;
  let canvasEl = null;
  let textLayerEl = null;

  // 已解析文档的 LRU 缓存：切回刚看过的论文时无需重新下载与解析
  // 只保留 2 篇，避免长文档占用过多浏览器内存
  const DOC_CACHE = new Map();
  const CACHE_LIMIT = 2;

  function dropCacheExcept(keepUrl) {
    while (DOC_CACHE.size > CACHE_LIMIT) {
      const oldest = DOC_CACHE.keys().next().value;
      if (oldest === keepUrl) break;
      const doc = DOC_CACHE.get(oldest);
      DOC_CACHE.delete(oldest);
      try { doc.destroy(); } catch (e) { /* 已被 pdf.js 释放 */ }
    }
  }

  // 文本层：叠在 canvas 上，让 PDF 文字可被选中（划词翻译用）
  function getTextLayer() {
    if (!canvasEl || !canvasEl.parentNode) return null;
    if (!textLayerEl || textLayerEl.parentNode !== canvasEl.parentNode) {
      textLayerEl = canvasEl.parentNode.querySelector('.pdf-text-layer');
      if (!textLayerEl) {
        textLayerEl = document.createElement('div');
        textLayerEl.className = 'pdf-text-layer';
        canvasEl.parentNode.appendChild(textLayerEl);
      }
    }
    return textLayerEl;
  }

  function clearTextLayer() {
    var el = getTextLayer();
    if (el) el.innerHTML = '';
  }

  function renderPage(pageNum) {
    if (!currentDoc || !canvasEl) return Promise.reject(new Error('未初始化'));

    currentPageNum = pageNum;
    clearTextLayer();

    return currentDoc.getPage(pageNum).then(function (page) {
      var viewport = page.getViewport({ scale: currentScale });
      canvasEl.width = viewport.width;
      canvasEl.height = viewport.height;
      var ctx = canvasEl.getContext('2d');

      return page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function () {
        return page.getTextContent().then(function (textContent) {
          var text = textContent.items.map(function (i) { return i.str; }).join(' ');
          var layer = getTextLayer();

          if (!layer || !pdfjsLib.renderTextLayer) {
            return { pageNum: pageNum, totalPages: totalPages, text: text, scale: currentScale };
          }

          layer.style.width = viewport.width + 'px';
          layer.style.height = viewport.height + 'px';
          var task = pdfjsLib.renderTextLayer({
            textContent: textContent,
            container: layer,
            viewport: viewport,
            textDivs: [],
          });

          return Promise.resolve(task.promise || task).then(function () {
            return { pageNum: pageNum, totalPages: totalPages, text: text, scale: currentScale };
          });
        });
      });
    });
  }

  window.PDFViewer = {
    // onProgress 回调收到 0-100 的下载/解析进度
    open: function (url, canvasElement, onProgress) {
      canvasEl = canvasElement;
      currentPageNum = 1;

      const cached = DOC_CACHE.get(url);
      if (cached) {
        // 命中缓存：LRU 置顶，直接复用已解析的文档
        DOC_CACHE.delete(url);
        DOC_CACHE.set(url, cached);
        currentDoc = cached;
        totalPages = cached.numPages;
        if (onProgress) onProgress(100);
        return Promise.resolve(totalPages);
      }

      currentDoc = null;
      const task = pdfjsLib.getDocument({ url: url });
      if (onProgress) {
        task.onProgress = function (p) {
          if (p && p.total) onProgress(Math.round((p.loaded / p.total) * 100));
        };
      }
      return task.promise.then(function (doc) {
        currentDoc = doc;
        totalPages = doc.numPages;
        DOC_CACHE.set(url, doc);
        dropCacheExcept(url);
        return totalPages;
      });
    },
    // 切换论文时立即清掉上一份的画面，避免加载期间仍显示旧 PDF
    clear: function () {
      currentDoc = null;
      totalPages = 0;
      if (canvasEl) {
        canvasEl.width = 0;
        canvasEl.height = 0;
      }
      clearTextLayer();
    },
    render: function (pageNum) {
      return renderPage(pageNum);
    },
    nextPage: function () {
      if (currentPageNum < totalPages) return renderPage(currentPageNum + 1);
      return Promise.reject(new Error('已是最后一页'));
    },
    prevPage: function () {
      if (currentPageNum > 1) return renderPage(currentPageNum - 1);
      return Promise.reject(new Error('已是第一页'));
    },
    zoomIn: function () {
      if (currentScale < 2.5) { currentScale += 0.2; }
      return renderPage(currentPageNum);
    },
    zoomOut: function () {
      if (currentScale > 0.5) { currentScale -= 0.2; }
      return renderPage(currentPageNum);
    },
    getScale: function () { return currentScale; },
    getCurrentPage: function () { return currentPageNum; },
    getTotalPages: function () { return totalPages; },
  };
})();
