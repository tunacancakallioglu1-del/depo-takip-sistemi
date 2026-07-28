(function () {
  window.disableGraphAnimations = function () {
    if (!window.Chart || !Chart.defaults) return;
    Chart.defaults.animation = false;
    if (Chart.defaults.transitions && Chart.defaults.transitions.active && Chart.defaults.transitions.active.animation) {
      Chart.defaults.transitions.active.animation.duration = 0;
    }
    if (Chart.defaults.transitions && Chart.defaults.transitions.resize && Chart.defaults.transitions.resize.animation) {
      Chart.defaults.transitions.resize.animation.duration = 0;
    }
  };

  window.disableGraphAnimations();
})();
