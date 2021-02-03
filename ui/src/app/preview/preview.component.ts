import { AfterViewInit, Component, OnInit } from '@angular/core';
import { ModalChildBase } from '../shared/class-base/modal-child-base';
import { GitLabCi } from '../shared/shared.types';

@Component({
  selector: 'app-preview',
  templateUrl: './preview.component.html',
  styleUrls: ['./preview.component.css']
})
export class PreviewComponent extends ModalChildBase implements OnInit, AfterViewInit {
  gitLabObject: GitLabCi;

  constructor() {
    super();
  }

  ngOnInit() {
  }

  ngAfterViewInit(): void {
    const ace = Reflect.get(window, 'ace');
    const yamlScriptMode = ace.require('ace/mode/yaml').Mode;
    const editor = ace.edit('compile-editor');
    ace.require('ace/ext/beautify');
    editor.setFontSize(16);
    editor.setReadOnly(true);
    editor.session.setMode(new yamlScriptMode());
    editor.setTheme('ace/theme/monokai');
    editor.setValue(this.gitLabObject.getPreviewString());
  }
}
