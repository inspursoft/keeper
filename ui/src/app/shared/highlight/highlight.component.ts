import { AfterContentInit, Component, ElementRef, Input, ViewChild } from '@angular/core';

declare let Prism: any;

@Component({
  selector: 'app-highlight',
  templateUrl: './highlight.component.html'
})
export class HighlightComponent implements AfterContentInit {
  @Input() public language: string;
  @Input() public code: string;
  @ViewChild('codeElement') codeElement: ElementRef;

  ngAfterContentInit() {
    this.codeElement.nativeElement.innerHTML = Prism.highlight(this.code, Prism.languages[this.language]);
  }
}
