import tkinter as tk
from tkinter import ttk, scrolledtext, font, filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk
import tokenize
import io
import ast
import sys
import traceback
import re
import os
import keyword
import builtins
import ctypes

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

class ICGVisitor(ast.NodeVisitor):
    def __init__(self):
        self.code = []
        self.temp_count = 0

    def new_temp(self):
        self.temp_count += 1
        return f"t{self.temp_count}"

    def visit_Module(self, node):
        for stmt in node.body:
            self.visit(stmt)
            
    def visit_Assign(self, node):
        value = self.visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.code.append(f"{target.id} = {value}")
        return value

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_map = {
            ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', 
            ast.FloorDiv: '//', ast.Mod: '%', ast.Pow: '**'
        }
        op = op_map.get(type(node.op), '?')
        temp = self.new_temp()
        self.code.append(f"{temp} = {left} {op} {right}")
        return temp

    def visit_Constant(self, node):
        return str(node.value)

    def visit_Name(self, node):
        return node.id
        
    def visit_Expr(self, node):
        self.visit(node.value)
        
    def visit_Call(self, node):
        args = [str(self.visit(arg)) for arg in node.args]
        temp = self.new_temp()
        func_name = "func"
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        self.code.append(f"{temp} = CALL {func_name}({', '.join(args)})")
        return temp

    def visit_JoinedStr(self, node):
        parts = []
        for val in node.values:
            if isinstance(val, ast.Constant):
                parts.append(str(val.value))
            elif isinstance(val, ast.FormattedValue):
                parts.append(f"{{{self.visit(val.value)}}}")
        return f"f'{''.join(parts)}'"

    def generic_visit(self, node):
        # Fallback for other nodes to ensure it doesn't crash on complex code
        self.code.append(f"; Unhandled Node: {type(node).__name__}")
        super().generic_visit(node)
        return "<expr>"


class CodeEditor(ctk.CTkFrame):
    def __init__(self, parent, font, bg, fg, insertbackground):
        super().__init__(parent, fg_color=bg, corner_radius=0)
        
        self.text = tk.Text(self, font=font, bg=bg, fg=fg, insertbackground=insertbackground, bd=0, undo=True, wrap=tk.NONE, padx=20, pady=5)
        self.linenumbers = tk.Canvas(self, width=60, bg=bg, bd=0, highlightthickness=0)
        self.scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.on_scrollbar)
        self.text.configure(yscrollcommand=self.on_textscroll)
        
        self.linenumbers.pack(side=tk.LEFT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text.bind("<KeyRelease>", self.on_key_release)
        self.text.bind("<MouseWheel>", self.on_key_release)
        self.text.bind("<Return>", self.on_key_release)
        self.text.bind("<BackSpace>", self.on_key_release)
        self.text.bind("<Configure>", self.on_key_release)
        
        self.setup_highlight_tags()
        self._highlight_job = None
        
    def on_scrollbar(self, *args):
        self.text.yview(*args)
        self.redraw_line_numbers()
        
    def on_textscroll(self, *args):
        self.scrollbar.set(*args)
        self.redraw_line_numbers()
        
    def on_key_release(self, event=None):
        self.redraw_line_numbers()
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(200, self.highlight_syntax)
        
    def redraw_line_numbers(self):
        self.linenumbers.delete("all")
        i = self.text.index("@0,0")
        while True:
            dline = self.text.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.linenumbers.create_text(45, y, anchor="ne", text=linenum, font=self.text.cget("font"), fill="#858585") # VS Code Line Number Color
            i = self.text.index("%s+1line" % i)
            
        height = self.winfo_height()
        self.linenumbers.create_line(59, 0, 59, height, fill="#404040", width=1)

    def setup_highlight_tags(self):
        # VS Code Dark+ inspired colors
        self.text.tag_configure("keyword", foreground="#C586C0") # Pink/Purple
        self.text.tag_configure("builtin", foreground="#4EC9B0") # Teal
        self.text.tag_configure("string", foreground="#CE9178") # Orange
        self.text.tag_configure("comment", foreground="#6A9955") # Green
        self.text.tag_configure("number", foreground="#B5CEA8") # Light Green
        self.text.tag_configure("function", foreground="#DCDCAA") # Yellow
        self.text.tag_configure("class", foreground="#4EC9B0") # Teal

    def highlight_syntax(self):
        content = self.text.get("1.0", tk.END)
        for tag in ["keyword", "builtin", "string", "comment", "number", "function", "class"]:
            self.text.tag_remove(tag, "1.0", tk.END)
            
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Keywords and Builtins
            for match in re.finditer(r"\b([a-zA-Z_]\w*)\b", line):
                word = match.group(1)
                if keyword.iskeyword(word):
                    self.text.tag_add("keyword", f"{line_num}.{match.start(1)}", f"{line_num}.{match.end(1)}")
                elif word in dir(builtins):
                    self.text.tag_add("builtin", f"{line_num}.{match.start(1)}", f"{line_num}.{match.end(1)}")
                    
            # Numbers
            for match in re.finditer(r"\b\d+\.?\d*\b", line):
                self.text.tag_add("number", f"{line_num}.{match.start()}", f"{line_num}.{match.end()}")
                
            # Function definitions
            for match in re.finditer(r"\bdef\s+([a-zA-Z_]\w*)", line):
                self.text.tag_add("keyword", f"{line_num}.{match.start()}", f"{line_num}.{match.start()+3}")
                self.text.tag_add("function", f"{line_num}.{match.start(1)}", f"{line_num}.{match.end(1)}")
                
            # Class definitions
            for match in re.finditer(r"\bclass\s+([a-zA-Z_]\w*)", line):
                self.text.tag_add("keyword", f"{line_num}.{match.start()}", f"{line_num}.{match.start()+5}")
                self.text.tag_add("class", f"{line_num}.{match.start(1)}", f"{line_num}.{match.end(1)}")
                
            # Function calls
            for match in re.finditer(r"\b([a-zA-Z_]\w*)\s*\(", line):
                func_name = match.group(1)
                if not keyword.iskeyword(func_name):
                    self.text.tag_add("function", f"{line_num}.{match.start(1)}", f"{line_num}.{match.end(1)}")
                    
            # Strings
            for match in re.finditer(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", line):
                self.text.tag_add("string", f"{line_num}.{match.start()}", f"{line_num}.{match.end()}")
                
            # Comments
            for match in re.finditer(r"#.*", line):
                self.text.tag_add("comment", f"{line_num}.{match.start()}", f"{line_num}.{match.end()}")

        self.text.tag_raise("string")
        self.text.tag_raise("comment")

    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)

    def insert(self, *args, **kwargs):
        self.text.insert(*args, **kwargs)
        self.highlight_syntax()
        self.redraw_line_numbers()


class VSCodeTabview(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.tab_buttons = {}
        self.tab_frames = {}
        self.current_tab = None
        
        self.header_frame = ctk.CTkFrame(self, fg_color="#2D2D2D", corner_radius=0, height=35)
        self.header_frame.pack(fill="x")
        
        self.content_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=0)
        self.content_frame.pack(fill="both", expand=True)

    def add(self, name):
        btn = ctk.CTkButton(self.header_frame, text=name, corner_radius=0, 
                            fg_color="#2D2D2D", hover_color="#333333", text_color="#969696",
                            font=("Segoe UI", 12, "bold"), width=0, border_spacing=10,
                            command=lambda: self.set(name))
        btn.pack(side="left")
        
        frame = ctk.CTkFrame(self.content_frame, fg_color="#1E1E1E", corner_radius=0)
        
        self.tab_buttons[name] = btn
        self.tab_frames[name] = frame
        
        if self.current_tab is None:
            self.set(name)
            
    def set(self, name):
        if self.current_tab:
            self.tab_frames[self.current_tab].pack_forget()
            self.tab_buttons[self.current_tab].configure(fg_color="#2D2D2D", text_color="#969696")
            
        self.tab_frames[name].pack(fill="both", expand=True)
        self.tab_buttons[name].configure(fg_color="#1E1E1E", text_color="#007ACC") # VS Code Blue Active Text
        self.current_tab = name
        
    def tab(self, name):
        return self.tab_frames[name]


class CompilerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Compiler Visualizer")
        self.root.geometry("1400x850")
        try:
            self.root.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.current_ast_image = None
        
        # VS Code Dark Theme Palette
        self.bg_color = "#1E1E1E"
        self.panel_bg = "#1E1E1E"
        self.header_bg = "#252526"
        self.text_color = "#D4D4D4"
        self.accent_color = "#007ACC"
        
        self.font_main = ("Consolas", 12)
        
        self.current_file = None
        self.is_dirty = False
        
        self.setup_ui()
        
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-n>", lambda e: self.new_file())
        
        self.code_input.text.bind("<KeyRelease>", self.mark_dirty, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_title()

    def mark_dirty(self, event=None):
        if event and event.keysym in ('Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 'Caps_Lock', 'Tab', 'Up', 'Down', 'Left', 'Right'):
            return
        if not self.is_dirty:
            self.is_dirty = True
            self.update_title()
            
    def update_title(self):
        title = "Python Compiler Visualizer"
        if self.current_file:
            title += f" - {self.current_file}"
        else:
            title += " - Untitled"
        if self.is_dirty:
            title += " *"
        self.root.title(title)

    def setup_ui(self):
        # Top Header
        header = ctk.CTkFrame(self.root, fg_color=self.header_bg, corner_radius=0, height=65)
        header.pack(fill=tk.X)
        header.pack_propagate(False) # Keep fixed height
        
        title = ctk.CTkLabel(header, text="PYTHON COMPILER VISUALIZER", font=("Segoe UI", 16, "bold"), text_color=self.accent_color)
        title.pack(side=tk.LEFT, padx=25, pady=15)

        # File Operations Buttons
        new_btn = ctk.CTkButton(header, text="📄 NEW", font=("Segoe UI", 12, "bold"), 
                                fg_color="#333333", hover_color="#04395E", width=100, command=self.new_file)
        new_btn.pack(side=tk.LEFT, padx=(30, 10), pady=15)

        open_btn = ctk.CTkButton(header, text="📂 OPEN", font=("Segoe UI", 12, "bold"), 
                                 fg_color="#333333", hover_color="#04395E", width=100, command=self.open_file)
        open_btn.pack(side=tk.LEFT, padx=(0, 10), pady=15)

        save_btn = ctk.CTkButton(header, text="💾 SAVE", font=("Segoe UI", 12, "bold"), 
                                 fg_color="#333333", hover_color="#04395E", width=100, command=self.save_file)
        save_btn.pack(side=tk.LEFT, pady=15)

        compile_btn = ctk.CTkButton(header, text="▶ COMPILE CODE", font=("Segoe UI", 12, "bold"), 
                                    fg_color=self.accent_color, hover_color="#005A9E", width=150, command=self.compile_code)
        compile_btn.pack(side=tk.RIGHT, padx=25, pady=15)

        # Main Layout
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.bg_color, bd=0, sashwidth=4)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Left Panel
        left_frame = ctk.CTkFrame(main_pane, fg_color=self.panel_bg, corner_radius=8, border_width=1, border_color="#333333")
        main_pane.add(left_frame, minsize=400, width=500)

        input_lbl = ctk.CTkLabel(left_frame, text="Input Source Code (.py)", font=("Segoe UI", 14, "bold"), text_color="#CCCCCC")
        input_lbl.pack(anchor=tk.W, padx=15, pady=(15, 5))

        self.code_input = CodeEditor(left_frame, font=self.font_main, bg=self.panel_bg, fg=self.text_color, insertbackground=self.text_color)
        self.code_input.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        default_code = "x = 10\ny = 5 + 3\narea = x * y\nprint(f'The area is: {area}')\n"
        self.code_input.insert(tk.END, default_code)

        # Right Panel
        right_frame = ctk.CTkFrame(main_pane, fg_color=self.bg_color, corner_radius=0)
        main_pane.add(right_frame, minsize=600)

        self.notebook = VSCodeTabview(right_frame, fg_color="transparent", corner_radius=0)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Add tabs
        tabs = [
            "0. Execution Output", "1. Lexical Analysis", "2. Syntax Analysis (AST)",
            "3. Intermediate Code", "4. Code Optimization", "5. Machine Code / Assembly"
        ]
        for t in tabs:
            self.notebook.add(t)

        self.tab_output = self.create_output_tab(self.notebook.tab("0. Execution Output"))
        self.tab_lexer = self.create_output_tab(self.notebook.tab("1. Lexical Analysis"))
        self.tab_parser = self.create_ast_tab(self.notebook.tab("2. Syntax Analysis (AST)"))
        self.tab_icg = self.create_output_tab(self.notebook.tab("3. Intermediate Code"))
        self.tab_opt = self.create_optimization_tab(self.notebook.tab("4. Code Optimization"))
        self.tab_asm = self.create_output_tab(self.notebook.tab("5. Machine Code / Assembly"))

    def check_save_changes(self):
        if not self.is_dirty:
            return True
        res = messagebox.askyesnocancel("Save Changes?", "You have unsaved changes. Do you want to save them?")
        if res is None: # Cancel
            return False
        if res is True: # Yes
            return self.save_file()
        return True # No (Discard)
        
    def new_file(self):
        if not self.check_save_changes():
            return
        self.code_input.text.delete("1.0", tk.END)
        self.current_file = None
        self.is_dirty = False
        self.update_title()

    def open_file(self):
        if not self.check_save_changes():
            return
        file_path = filedialog.askopenfilename(defaultextension=".py", filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.code_input.text.delete(1.0, tk.END)
            self.code_input.insert(tk.END, content)
            self.current_file = file_path
            self.is_dirty = False
            self.update_title()

    def save_file(self):
        if self.current_file:
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(self.code_input.get("1.0", tk.END+"-1c"))
            self.is_dirty = False
            self.update_title()
            return True
        else:
            return self.save_as_file()
            
    def save_as_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.code_input.get("1.0", tk.END+"-1c"))
            self.current_file = file_path
            self.is_dirty = False
            self.update_title()
            return True
        return False
        
    def on_closing(self):
        if self.check_save_changes():
            self.root.destroy()

    def create_ast_tab(self, frame):
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        download_btn = ctk.CTkButton(toolbar, text="📥 DOWNLOAD IMAGE (.JPG)", font=("Segoe UI", 11, "bold"),
                                     fg_color="#007ACC", hover_color="#005A9E", command=self.download_ast_image)
        download_btn.pack(side=tk.LEFT)
        
        txt = ctk.CTkTextbox(frame, font=self.font_main, fg_color=self.bg_color, text_color=self.text_color)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.configure(state="disabled")
        return txt

    def download_ast_image(self):
        if not self.current_ast_image:
            messagebox.showwarning("No Image", "Please compile the code first to generate the AST image.")
            return
            
        file_path = filedialog.asksaveasfilename(defaultextension=".jpg", initialfile="AST_Tree.jpg", filetypes=[("JPEG Image", "*.jpg"), ("PNG Image", "*.png"), ("All Files", "*.*")])
        if file_path:
            try:
                self.current_ast_image.save(file_path)
                messagebox.showinfo("Success", f"AST Image saved successfully at:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image:\n{str(e)}")

    def create_output_tab(self, frame):
        txt = ctk.CTkTextbox(frame, font=self.font_main, fg_color=self.bg_color, text_color=self.text_color)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.configure(state="disabled")
        return txt

    def create_optimization_tab(self, frame):
        pane = tk.PanedWindow(frame, orient=tk.HORIZONTAL, bg="#252526", bd=0, sashwidth=4)
        pane.pack(fill=tk.BOTH, expand=True)

        frame_before = ctk.CTkFrame(pane, fg_color=self.bg_color, corner_radius=0)
        pane.add(frame_before, minsize=200)
        lbl_b = ctk.CTkLabel(frame_before, text="Before Optimization", text_color="#858585", font=("Segoe UI", 12, "bold"))
        lbl_b.pack(anchor=tk.W, pady=8, padx=10)
        txt_before = ctk.CTkTextbox(frame_before, font=self.font_main, fg_color=self.bg_color, text_color=self.text_color)
        txt_before.pack(fill=tk.BOTH, expand=True)

        frame_after = ctk.CTkFrame(pane, fg_color=self.bg_color, corner_radius=0)
        pane.add(frame_after, minsize=200)
        lbl_a = ctk.CTkLabel(frame_after, text="After Optimization", text_color=self.accent_color, font=("Segoe UI", 12, "bold"))
        lbl_a.pack(anchor=tk.W, pady=8, padx=10)
        txt_after = ctk.CTkTextbox(frame_after, font=self.font_main, fg_color=self.bg_color, text_color=self.text_color)
        txt_after.pack(fill=tk.BOTH, expand=True)

        return (txt_before, txt_after)

    def write_output(self, widget, text, is_error=False):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        
        # Access internal tk.Text for tagging in CTkTextbox
        if hasattr(widget, "_textbox"):
            widget._textbox.tag_configure("error", foreground="#F14C4C") # VS Code Red
            if is_error:
                widget.insert("end", text, "error")
            else:
                widget.insert("end", text)
        else:
            widget.insert("end", text)
            
        widget.configure(state="disabled")

    def compile_code(self):
        code = self.code_input.get(1.0, tk.END).strip()
        if not code:
            return

        actual_out, is_exec_err = self.run_execution(code)
        self.write_output(self.tab_output, actual_out, is_exec_err)

        tokens_out, is_lex_err = self.run_lexer(code)
        self.write_output(self.tab_lexer, tokens_out, is_lex_err)

        ast_out, tree, is_parse_err = self.run_parser(code)
        self.write_output(self.tab_parser, ast_out, is_parse_err)

        icg_code, is_icg_err = self.run_icg(tree)
        self.write_output(self.tab_icg, "\n".join(icg_code) if icg_code else "No intermediate code generated.", is_icg_err)

        opt_code, is_opt_err = self.run_optimization(icg_code)
        self.write_output(self.tab_opt[0], "\n".join(icg_code) if icg_code else "No intermediate code to optimize.", is_icg_err)
        self.write_output(self.tab_opt[1], "\n".join(opt_code) if opt_code else "No optimized code.", is_opt_err)

        asm_out = self.run_assembly(opt_code)
        self.write_output(self.tab_asm, asm_out, is_opt_err)

    def run_execution(self, code):
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        try:
            # We use an empty dictionary to isolate the execution environment
            exec(code, {})
            output = redirected_output.getvalue()
            if not output.strip():
                output = "(Program executed successfully but produced no output. Did you forget to print()?)"
            return output, False
        except Exception as e:
            error_msg = traceback.format_exc()
            return f"--- EXECUTION ERROR ---\n{error_msg}", True
        finally:
            sys.stdout = old_stdout

    def run_lexer(self, code):
        tokens_str = []
        try:
            stream = io.BytesIO(code.encode('utf-8'))
            for tok in tokenize.tokenize(stream.readline):
                if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NL):
                    continue
                if tok.type == tokenize.NEWLINE:
                    tokens_str.append(f"Type: {'NEWLINE':<12} | Value: \\n")
                    continue
                token_type = tokenize.tok_name[tok.type]
                tokens_str.append(f"Type: {token_type:<12} | Value: {repr(tok.string):<15} | Line: {tok.start[0]}")
            return "\n".join(tokens_str), False
        except Exception as e:
            return f"Lexical Error:\n{str(e)}", True

    def run_parser(self, code):
        try:
            tree = ast.parse(code)
            
            # --- Generate Graphic Image (PIL) ---
            class TreeNode:
                def __init__(self, label):
                    self.label = label
                    self.children = []
                    self.x = 0
                    self.y = 0
                    self.width = 0

            def build_tree(node):
                if not isinstance(node, ast.AST):
                    return None
                label = node.__class__.__name__
                extra = []
                if hasattr(node, 'id'): extra.append(f"id='{node.id}'")
                if hasattr(node, 'arg'): extra.append(f"arg='{node.arg}'")
                if hasattr(node, 'name'): extra.append(f"name='{node.name}'")
                if isinstance(node, ast.Constant): extra.append(f"val={repr(node.value)}")
                if extra:
                    label += f"\n{', '.join(extra)}"
                    
                t_node = TreeNode(label)
                
                for field, value in ast.iter_fields(node):
                    if isinstance(value, list):
                        for item in value:
                            child = build_tree(item)
                            if child:
                                t_node.children.append(child)
                    elif isinstance(value, ast.AST):
                        child = build_tree(value)
                        if child:
                            t_node.children.append(child)
                            
                return t_node

            def calculate_layout(node, level=0):
                if not node.children:
                    node.width = 120
                    return 120
                
                width = 0
                for child in node.children:
                    width += calculate_layout(child, level + 1)
                    
                node.width = max(120, width)
                return node.width

            def assign_coords(node, x_start, y_start, level_height=80):
                node.x = x_start + node.width / 2
                node.y = y_start
                
                current_x = x_start
                for child in node.children:
                    assign_coords(child, current_x, y_start + level_height, level_height)
                    current_x += child.width
                    
            t_node = build_tree(tree)
            if t_node:
                calculate_layout(t_node)
                img_width = int(t_node.width)
                
                def get_depth(n):
                    if not n.children: return 1
                    return 1 + max(get_depth(c) for c in n.children)
                
                depth = get_depth(t_node)
                level_height = 80
                img_height = depth * level_height + 50
                
                img = Image.new('RGB', (max(img_width, 400), max(img_height, 400)), (13, 17, 23))
                draw = ImageDraw.Draw(img)
                
                try:
                    font = ImageFont.truetype('arial.ttf', 12)
                except:
                    font = ImageFont.load_default()
                    
                assign_coords(t_node, 0, 50, level_height)
                
                def render(n):
                    for child in n.children:
                        draw.line([(n.x, n.y + 15), (child.x, child.y - 15)], fill=(88, 166, 255), width=2)
                        render(child)
                        
                    try:
                        text_bbox = draw.textbbox((0,0), n.label, font=font)
                        tw = text_bbox[2] - text_bbox[0]
                        th = text_bbox[3] - text_bbox[1]
                    except AttributeError:
                        tw, th = 60, 20
                        
                    box_w = max(tw + 20, 80)
                    box_h = max(th + 15, 30)
                    
                    draw.rectangle([n.x - box_w/2, n.y - box_h/2, n.x + box_w/2, n.y + box_h/2], fill=(33, 38, 45), outline=(139, 148, 158))
                    draw.text((n.x - tw/2, n.y - th/2), n.label, fill=(201, 209, 217), font=font)
                    
                render(t_node)
                self.current_ast_image = img
            else:
                self.current_ast_image = None
            
            # --- Generate graphic type text tree ---
            def generate_tree(node, prefix="", is_last=True, is_root=True):
                if not isinstance(node, ast.AST):
                    return ""
                    
                node_name = node.__class__.__name__
                extra = []
                if hasattr(node, 'id'): extra.append(f"id='{node.id}'")
                if hasattr(node, 'arg'): extra.append(f"arg='{node.arg}'")
                if hasattr(node, 'name'): extra.append(f"name='{node.name}'")
                if isinstance(node, ast.Constant): extra.append(f"value={repr(node.value)}")
                    
                extra_str = f" [{', '.join(extra)}]" if extra else ""
                
                if is_root:
                    res = f"{node_name}{extra_str}\n"
                    prefix_child = ""
                else:
                    res = f"{prefix}{'└── ' if is_last else '├── '}{node_name}{extra_str}\n"
                    prefix_child = prefix + ("    " if is_last else "│   ")
                    
                children = []
                for field, value in ast.iter_fields(node):
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, ast.AST):
                                children.append(item)
                    elif isinstance(value, ast.AST):
                        children.append(value)
                        
                for i, child in enumerate(children):
                    is_last_child = (i == len(children) - 1)
                    res += generate_tree(child, prefix_child, is_last_child, is_root=False)
                    
                return res

            graphic_tree = generate_tree(tree)

            # Use ast.dump for a nice textual tree if python >= 3.9 supports indent
            try:
                dump = ast.dump(tree, indent=4)
            except TypeError:
                dump = ast.dump(tree) # Fallback for older python versions
                
            combined_output = f"=== GRAPHICAL AST ===\n{graphic_tree}\n=== TEXT AST ===\n{dump}"
            return combined_output, tree, False
        except Exception as e:
            return f"Syntax Error:\n{str(e)}", None, True

    def run_icg(self, tree):
        if not tree: return [], True
        try:
            visitor = ICGVisitor()
            visitor.visit(tree)
            return visitor.code, False
        except Exception as e:
            return [f"ICG Error: {str(e)}"], True

    def run_optimization(self, icg_code):
        if not icg_code or (len(icg_code) > 0 and icg_code[0].startswith("ICG Error")): return [], True
        optimized = []
        constants = {} # For constant propagation
        
        for line in icg_code:
            original_line = line
            
            # 1. Constant Propagation
            if " = " in line:
                left, right = line.split(" = ", 1)
                
                # Replace known constants in the right side
                for var, val in constants.items():
                    # Replace word boundaries to avoid partial matches
                    right = re.sub(rf'\b{var}\b', str(val), right)
                
                line = f"{left} = {right}"

            # 2. Constant Folding
            if " = " in line and "CALL" not in line:
                left, right = line.split(" = ", 1)
                left = left.strip()
                
                # If right side is purely math with numbers
                if any(op in right for op in '+-*/') and all(c in "0123456789+-*/. " for c in right):
                    try:
                        val = eval(right)
                        if isinstance(val, float) and val.is_integer():
                            val = int(val)
                        
                        constants[left] = val
                        optimized.append(f"{left} = {val}  ; (Folded & Propagated)")
                        continue
                    except:
                        pass
                # If right side is a direct constant number assignment
                elif right.strip().replace('.', '', 1).isdigit() or (right.strip().startswith('-') and right.strip()[1:].replace('.', '', 1).isdigit()):
                    try:
                        val = float(right) if '.' in right else int(right)
                        constants[left] = val
                    except:
                        pass
            
            # If line was modified via propagation but not folded
            if line != original_line:
                optimized.append(f"{line}  ; (Propagated)")
            else:
                optimized.append(line)
                
        return optimized, False

    def run_assembly(self, opt_code):
        if not opt_code: return "No assembly generated.", True
        asm = [
            "; --- BEGIN ASSEMBLY ---",
            "section .data",
            "section .text",
            "global _start",
            "_start:"
        ]
        
        for line in opt_code:
            line = line.split("  ;")[0].strip() # Remove optimization comments
            
            if " = " in line:
                left, right = line.split(" = ", 1)
                if "CALL" in right:
                    func_call = right.replace("CALL ", "")
                    asm.append(f"    ; {line}")
                    func_name, args = func_call.split("(", 1)
                    args = args.rstrip(")")
                    for arg in args.split(","):
                        arg = arg.strip()
                        if arg:
                            asm.append(f"    PUSH {arg}")
                    asm.append(f"    CALL {func_name}")
                    asm.append(f"    MOV [{left}], EAX")
                elif any(op in right for op in ['+', '-', '*', '/']):
                    asm.append(f"    ; {line}")
                    parts = right.split()
                    if len(parts) == 3:
                        op1, op, op2 = parts
                        asm.append(f"    MOV EAX, [{op1}]" if not op1.replace('.', '', 1).isdigit() else f"    MOV EAX, {op1}")
                        
                        val2 = f"[{op2}]" if not op2.replace('.', '', 1).isdigit() else op2
                        
                        if op == '+': asm.append(f"    ADD EAX, {val2}")
                        elif op == '-': asm.append(f"    SUB EAX, {val2}")
                        elif op == '*': asm.append(f"    IMUL EAX, {val2}")
                        elif op == '/': 
                            asm.append(f"    MOV EBX, {val2}")
                            asm.append(f"    CDQ")
                            asm.append(f"    IDIV EBX")
                            
                        asm.append(f"    MOV [{left}], EAX")
                else:
                    asm.append(f"    ; {line}")
                    val = f"[{right}]" if not right.replace('.', '', 1).isdigit() else right
                    asm.append(f"    MOV [{left}], {val}")
            else:
                asm.append(f"    ; {line}")

        asm.append("    ; Exit program")
        asm.append("    MOV EAX, 1")
        asm.append("    INT 0x80")
        return "\n".join(asm), False

if __name__ == "__main__":
    root = ctk.CTk()
    app = CompilerApp(root)
    root.mainloop()
