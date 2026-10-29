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
    open: function (url, canvasElement) {
      canvasEl = canvasElement;
      currentDoc = null;
      currentPageNum = 1;
      return pdfjsLib.getDocument({ url: url }).promise.then(function (doc) {
        currentDoc = doc;
        totalPages = doc.numPages;
        return totalPages;
      });
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
