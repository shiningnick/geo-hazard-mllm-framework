# -*- coding: utf-8 -*-
"""
地质灾害风险识别系统 - 图形用户界面（投稿代码包核心入口）
"""
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from config import DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, OUTPUT_DIR, DEMO_IMAGES_DIR
from modules.map_view import create_hazard_map
from modules.system_scheduler import SystemScheduler


class GeohazardSurveyGUI:
    """地质灾害调查系统 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("地质灾害风险识别系统")
        self.root.geometry("900x700")

        self.scheduler = None
        self.current_model_provider = DEFAULT_MODEL_PROVIDER
        self.current_model_name = DEFAULT_MODEL_NAME
        self.map_canvas = None
        self.map_image_path = None

        self.selected_files = []
        self.selected_directory = None

        self.create_widgets()
        self.init_scheduler()

    def create_widgets(self):
        canvas_container = ttk.Frame(self.root)
        canvas_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        canvas_container.columnconfigure(0, weight=1)
        canvas_container.rowconfigure(0, weight=1)

        self.scroll_canvas = tk.Canvas(canvas_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)

        main_frame = ttk.Frame(self.scroll_canvas, padding="10")
        self.scroll_canvas_window = self.scroll_canvas.create_window((0, 0), window=main_frame, anchor="nw")

        def configure_scroll_region(_event):
            self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

        def configure_canvas_width(event):
            self.scroll_canvas.itemconfig(self.scroll_canvas_window, width=event.width)

        main_frame.bind("<Configure>", configure_scroll_region)
        self.scroll_canvas.bind("<Configure>", configure_canvas_width)

        def on_mousewheel(event):
            if sys.platform.startswith("linux"):
                if event.num == 4:
                    self.scroll_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.scroll_canvas.yview_scroll(1, "units")
            else:
                self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        if sys.platform.startswith("linux"):
            self.scroll_canvas.bind_all("<Button-4>", on_mousewheel)
            self.scroll_canvas.bind_all("<Button-5>", on_mousewheel)
        else:
            self.scroll_canvas.bind_all("<MouseWheel>", on_mousewheel)

        main_frame.columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="地质灾害风险识别系统", font=("Arial", 16, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(0, 20)
        )

        config_frame = ttk.LabelFrame(main_frame, text="模型配置", padding="10")
        config_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(config_frame, text="模型提供商:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.provider_var = tk.StringVar(value=DEFAULT_MODEL_PROVIDER)
        provider_combo = ttk.Combobox(
            config_frame, textvariable=self.provider_var,
            values=["openai", "gemini", "anthropic", "grok", "qwen"],
            state="readonly", width=20,
        )
        provider_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        provider_combo.bind("<<ComboboxSelected>>", self.on_provider_changed)

        ttk.Label(config_frame, text="模型名称:").grid(row=0, column=2, sticky=tk.W, padx=(10, 5))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL_NAME)
        self.model_combo = ttk.Combobox(
            config_frame, textvariable=self.model_var,
            values=self._get_models_for_provider(DEFAULT_MODEL_PROVIDER), width=25,
        )
        self.model_combo.grid(row=0, column=3, sticky=tk.W)

        file_frame = ttk.LabelFrame(main_frame, text="图片选择", padding="10")
        file_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)

        ttk.Button(file_frame, text="选择单张图片", command=self.select_single_image).grid(row=0, column=0, padx=(0, 10))
        self.single_file_label = ttk.Label(file_frame, text="未选择文件", foreground="gray")
        self.single_file_label.grid(row=0, column=1, sticky=tk.W)

        ttk.Button(file_frame, text="批量选择图片", command=self.select_multiple_images).grid(row=1, column=0, padx=(0, 10), pady=(5, 0))
        self.batch_file_label = ttk.Label(file_frame, text="未选择文件", foreground="gray")
        self.batch_file_label.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))

        ttk.Button(file_frame, text="选择目录", command=self.select_directory).grid(row=2, column=0, padx=(0, 10), pady=(5, 0))
        self.dir_label = ttk.Label(file_frame, text="未选择目录", foreground="gray")
        self.dir_label.grid(row=2, column=1, sticky=tk.W, pady=(5, 0))

        ttk.Button(file_frame, text="加载演示数据", command=self.load_demo_images).grid(row=3, column=0, padx=(0, 10), pady=(8, 0))
        ttk.Label(file_frame, text="demo_data/images/ 下 4 张样例", foreground="gray").grid(row=3, column=1, sticky=tk.W, pady=(8, 0))

        options_frame = ttk.LabelFrame(main_frame, text="处理选项", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        self.enable_external_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="补充外部环境数据", variable=self.enable_external_var).grid(row=0, column=0, sticky=tk.W)

        self.enable_risk_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="进行风险评价（FHWA）", variable=self.enable_risk_var).grid(row=0, column=1, sticky=tk.W, padx=(20, 0))

        self.enable_map_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="绘制风险空间分布图", variable=self.enable_map_var).grid(row=0, column=2, sticky=tk.W, padx=(20, 0))

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))
        self.process_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing)
        self.process_button.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="打开输出文件夹", command=self.open_output_folder).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空日志", command=self.clear_log).pack(side=tk.LEFT)

        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.progress_label = ttk.Label(progress_frame, text="就绪")
        self.progress_label.grid(row=1, column=0, pady=(5, 0))

        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=2)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        map_frame = ttk.LabelFrame(main_frame, text="灾害空间分布（FHWA 风险评价结果）", padding="5")
        map_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(7, weight=3)
        self.map_placeholder = ttk.Label(map_frame, text="等待处理结果...", foreground="gray")
        self.map_placeholder.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.map_frame = map_frame

    def _get_models_for_provider(self, provider: str) -> list:
        from config import MODEL_CONFIGS
        return MODEL_CONFIGS.get(provider, {}).get("models", [])

    def on_provider_changed(self, _event=None):
        models = self._get_models_for_provider(self.provider_var.get())
        self.model_combo["values"] = models
        if models:
            self.model_var.set(models[0])

    def init_scheduler(self):
        try:
            self.scheduler = SystemScheduler(
                model_provider=self.current_model_provider,
                model_name=self.current_model_name,
            )
            self.log("系统初始化成功")
        except Exception as e:
            self.log(f"系统初始化失败: {e}", error=True)
            messagebox.showerror("错误", f"系统初始化失败: {e}")

    def log(self, message, error=False):
        self.log_text.insert(tk.END, f"{message}\n")
        if error:
            self.log_text.tag_add("error", "end-2l", "end-1l")
            self.log_text.tag_config("error", foreground="red")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def load_demo_images(self):
        demo_dir = Path(DEMO_IMAGES_DIR)
        if not demo_dir.exists():
            messagebox.showwarning("警告", f"演示目录不存在: {demo_dir}")
            return
        files = sorted(demo_dir.glob("*.jpg")) + sorted(demo_dir.glob("*.png"))
        if not files:
            messagebox.showwarning("警告", "演示目录中没有图片")
            return
        self.selected_files = [str(f) for f in files]
        self.selected_directory = None
        self.batch_file_label.config(text=f"已加载 {len(files)} 张演示图片", foreground="black")
        self.log(f"已加载演示数据: {len(files)} 张")

    def select_single_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"), ("所有文件", "*.*")],
        )
        if file_path:
            self.selected_files = [file_path]
            self.selected_directory = None
            self.single_file_label.config(text=os.path.basename(file_path), foreground="black")

    def select_multiple_images(self):
        file_paths = filedialog.askopenfilenames(
            title="批量选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"), ("所有文件", "*.*")],
        )
        if file_paths:
            self.selected_files = list(file_paths)
            self.selected_directory = None
            self.batch_file_label.config(text=f"已选择 {len(file_paths)} 张图片", foreground="black")

    def select_directory(self):
        dir_path = filedialog.askdirectory(title="选择图片目录")
        if dir_path:
            self.selected_directory = dir_path
            self.selected_files = []
            self.dir_label.config(text=os.path.basename(dir_path), foreground="black")

    def start_processing(self):
        if not self.selected_files and not self.selected_directory:
            messagebox.showwarning("警告", "请先选择图片、目录，或点击「加载演示数据」")
            return

        self.current_model_provider = self.provider_var.get()
        self.current_model_name = self.model_var.get()
        try:
            self.scheduler = SystemScheduler(
                model_provider=self.current_model_provider,
                model_name=self.current_model_name,
            )
        except Exception as e:
            messagebox.showerror("错误", f"初始化调度器失败: {e}")
            return

        self.process_button.config(state="disabled")
        threading.Thread(target=self.process_images_thread, daemon=True).start()

    def process_images_thread(self):
        results = []
        try:
            enable_external = self.enable_external_var.get()
            enable_risk = self.enable_risk_var.get()
            paths = list(self.selected_files)

            if self.selected_directory:
                image_list = self.scheduler.image_manager.scan_directory(self.selected_directory)
                paths = [img["path"] for img in image_list if img.get("exists")]

            total = len(paths)
            for i, image_path in enumerate(paths, 1):
                self.log(f"\n处理 {i}/{total}: {os.path.basename(image_path)}")
                self.update_progress(i, total)
                try:
                    result = self.scheduler.process_single_image(
                        image_path,
                        enable_risk_assessment=enable_risk,
                        enable_external_data=enable_external,
                    )
                    if "error" in result:
                        self.log(f"失败: {result['error']}", error=True)
                    else:
                        self.log(f"成功 | 类型: {result.get('风险类型')} | 风险: {result.get('风险等级', '未评价')}")
                    results.append(result)
                except Exception as e:
                    self.log(f"异常: {e}", error=True)
                    results.append({"error": str(e), "image_path": image_path})

            if self.enable_map_var.get():
                self.update_map(results)
            messagebox.showinfo("完成", "处理完成，结果已保存至 output/ 目录。")
        except Exception as e:
            self.log(f"处理失败: {e}", error=True)
            messagebox.showerror("错误", str(e))
        finally:
            self.process_button.config(state="normal")
            self.progress_label.config(text="就绪")

    def update_map(self, records):
        valid = [r for r in records if isinstance(r, dict) and "error" not in r]
        if not valid:
            return
        try:
            fig = create_hazard_map(valid)
        except Exception as e:
            self.log(f"地图绘制失败: {e}", error=True)
            return

        if self.map_canvas is not None:
            try:
                self.map_canvas.get_tk_widget().destroy()
            except Exception:
                pass
        if hasattr(self, "map_placeholder"):
            self.map_placeholder.grid_remove()

        canvas = FigureCanvasTkAgg(fig, master=self.map_frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.map_canvas = canvas

        map_path = Path(OUTPUT_DIR) / "区域风险评价图.png"
        fig.savefig(str(map_path), dpi=150, facecolor="white")
        self.map_image_path = str(map_path)
        self.root.update_idletasks()
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def update_progress(self, current, total):
        if total > 0:
            self.progress_var.set((current / total) * 100)
            self.progress_label.config(text=f"处理中: {current}/{total}")

    def open_output_folder(self):
        output_path = Path(OUTPUT_DIR)
        output_path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(output_path))
        elif sys.platform == "darwin":
            os.system(f'open "{output_path}"')
        else:
            os.system(f'xdg-open "{output_path}"')


def main():
    root = tk.Tk()
    GeohazardSurveyGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
